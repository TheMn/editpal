/**
 * editpal upload link: a tiny Google Apps Script web app that lets editpal put finished files into
 * ONE folder of your Google Drive, and nothing else.  STATUS: not yet tested end to end
 * (written against the Drive v3 and Apps Script documentation; the script host was not reachable
 * where it was written).
 *
 * Deploy once (about 5 minutes, signed in to the Google account that should own the files):
 *   1. Open https://script.google.com, "New project". Paste this whole file over Code.gs.
 *   2. Project Settings -> tick "Show appsscript.json manifest file", and make it contain
 *        { "timeZone": "Etc/UTC", "exceptionLogging": "STACKDRIVER", "runtimeVersion": "V8",
 *          "oauthScopes": ["https://www.googleapis.com/auth/drive.file",
 *                          "https://www.googleapis.com/auth/script.external_request"],
 *          "webapp": { "executeAs": "USER_DEPLOYING", "access": "ANYONE_ANONYMOUS" } }
 *      (drive.file = the script can only see and change files it created itself.)
 *   3. Deploy -> New deployment -> type "Web app" -> Execute as "Me", Who has access "Anyone".
 *      Approve the permission prompt. Copy the Web app URL (it ends in /exec).
 *   4. Put that URL in the environment variable named by channel.json -> upload.env
 *      (EDITPAL_UPLOAD_URL), in the Claude Code cloud environment's settings. Treat the URL like a
 *      password: anyone who has it can add files to the output folder (and only there).
 *   5. Test:  ./pal drive put <episode> some-small-file.txt
 * The first call creates the folder named OUT_FOLDER in your My Drive. Files appear in
 * OUT_FOLDER/<episode>/. To revoke access: Deploy -> Manage deployments -> archive it.
 *
 * What it does: receives {"action":"start","folder","name","size","mime"} as a POST, finds or creates
 * the episode subfolder, starts a Drive resumable upload session for the file, and returns
 * {"upload": "<session url>"}. The caller then sends the bytes straight to Drive. The script never
 * returns an access token, never reads or deletes anything, and only creates files inside OUT_FOLDER.
 */

var OUT_FOLDER = 'editpal-out';          // name of the output folder (channel.json upload.folder)
var FOLDER_MIME = 'application/vnd.google-apps.folder';
var API = 'https://www.googleapis.com/drive/v3/files';
var UPLOAD_API = 'https://www.googleapis.com/upload/drive/v3/files?uploadType=resumable';

function doPost(e) {
  try {
    var req = JSON.parse((e && e.postData && e.postData.contents) || '{}');
    if (req.action !== 'start') return reply_({ error: 'unknown action' });
    var name = clean_(req.name, 200);
    var folder = clean_(req.folder, 100);
    if (!name || !folder) return reply_({ error: 'name and folder are required' });
    var lock = LockService.getScriptLock();
    lock.waitLock(20000);
    var parent;
    try {
      parent = child_(rootId_(), folder);
    } finally {
      lock.releaseLock();
    }
    return reply_({ upload: startSession_(parent, name, String(req.mime || 'application/octet-stream'), Number(req.size) || 0) });
  } catch (err) {
    return reply_({ error: String(err && err.message ? err.message : err) });
  }
}

function doGet() {
  return reply_({ ok: true, note: 'editpal upload link: use POST' });
}

/** JSON response. */
function reply_(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}

/** A file or folder name without path characters or control characters, at most n long. */
function clean_(s, n) {
  return String(s || '').replace(/[\/\\\u0000-\u001f]/g, '-').replace(/^\.+/, '').trim().slice(0, n);
}

/** Authorised Drive API call; returns the parsed JSON body. */
function api_(method, url, payload) {
  var res = UrlFetchApp.fetch(url, {
    method: method,
    contentType: 'application/json; charset=UTF-8',
    headers: { Authorization: 'Bearer ' + ScriptApp.getOAuthToken() },
    payload: payload ? JSON.stringify(payload) : undefined,
    muteHttpExceptions: true
  });
  if (res.getResponseCode() >= 300) throw new Error('Drive said ' + res.getResponseCode());
  return JSON.parse(res.getContentText());
}

/** Id of the output folder: created on first use, remembered in the script properties. */
function rootId_() {
  var props = PropertiesService.getScriptProperties();
  var id = props.getProperty('ROOT_FOLDER_ID');
  if (id) return id;
  id = api_('post', API, { name: OUT_FOLDER, mimeType: FOLDER_MIME }).id;
  props.setProperty('ROOT_FOLDER_ID', id);
  return id;
}

/** Id of the subfolder `name` inside `parent` (created if it does not exist yet). */
function child_(parent, name) {
  var q = "'" + parent + "' in parents and name = '" + name.replace(/\\/g, '\\\\').replace(/'/g, "\\'") +
          "' and mimeType = '" + FOLDER_MIME + "' and trashed = false";
  var found = api_('get', API + '?fields=files(id)&pageSize=1&q=' + encodeURIComponent(q));
  if (found.files && found.files.length) return found.files[0].id;
  return api_('post', API, { name: name, mimeType: FOLDER_MIME, parents: [parent] }).id;
}

/** Starts a resumable upload of one file into `parent`; returns the session URL (which is the only secret it holds). */
function startSession_(parent, name, mime, size) {
  var headers = { Authorization: 'Bearer ' + ScriptApp.getOAuthToken(), 'X-Upload-Content-Type': mime };
  if (size > 0) headers['X-Upload-Content-Length'] = String(size);
  var res = UrlFetchApp.fetch(UPLOAD_API, {
    method: 'post',
    contentType: 'application/json; charset=UTF-8',
    headers: headers,
    payload: JSON.stringify({ name: name, parents: [parent] }),
    muteHttpExceptions: true
  });
  if (res.getResponseCode() !== 200) throw new Error('Drive refused the upload (' + res.getResponseCode() + ')');
  var h = res.getAllHeaders();
  var loc = h.Location || h.location;
  if (!loc) throw new Error('Drive gave no upload address');
  return loc;
}
