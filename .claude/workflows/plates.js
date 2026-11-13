export const meta = {
  name: 'plates',
  description: 'Write every custom motion plate of one episode in parallel, then have each one reviewed cold. Run after the plan exists and before the storyboard gate: /plates <episode>',
  phases: ['Find the custom plates', 'Write the plates', 'Review the stills'],
}

// Optional speed-up for episodes with many custom plates. It only writes and poses plates;
// it never renders video and it cannot stop for approval, so the storyboard gate stays in the
// `video` skill (stages/plan.md). Kit plates need no agent and are skipped.

const episode = typeof args === 'string' ? args : args && args.episode
if (!episode) throw new Error('give the episode: /plates <episode>')

phase('Find the custom plates')
const found = await agent(
  `In the editpal repository, find the episode folder matching "${episode}" under episodes/ and read its plan.json. ` +
    `List every beat whose plate.type is "custom" and whose status is not "rendered". Do not change any file.`,
  {
    label: 'read the plan',
    schema: {
      type: 'object',
      required: ['folder', 'beats'],
      properties: {
        folder: { type: 'string' },
        beats: { type: 'array', items: { type: 'string' } },
      },
    },
  },
)

if (!found.beats.length) {
  log('No custom plates to write: every beat uses the kit or is already rendered.')
  return { episode: found.folder, written: [], problems: [] }
}

phase('Write the plates')
const written = await pipeline(found.beats, beat =>
  agent(
    `Act as the plate-maker described in .claude/agents/plate-maker.md (read that file and follow it exactly). ` +
      `Episode: ${found.folder}. Beat: ${beat}. Write the plate, check it, pose it, and report the file, its variables and the still's path.`,
    { label: beat, agentType: 'plate-maker' },
  ),
)

phase('Review the stills')
const review = await agent(
  `Act as the fresh-eyes reviewer described in .claude/agents/fresh-eyes.md (read that file and follow it exactly). ` +
    `You are given a storyboard: the stills in ${found.folder}/build/review/stills/ for beats ${found.beats.join(', ')} ` +
    `and ${found.folder}/plan.json. Return the ranked problems only.`,
  { label: 'cold review', agentType: 'fresh-eyes' },
)

return {
  episode: found.folder,
  written: written.filter(Boolean),
  problems: review,
  next: 'Fix the P0 and P1 lines, then ./pal board story and stop at the storyboard gate.',
}
