/**
 * WebApp.gs -- entry point for the web app deployment.
 *
 * Deployment settings that matter (also the defaults in appsscript.json):
 *   Execute as:  USER_ACCESSING  (each visitor's own token is used;
 *                                 first visit triggers their consent)
 *   Access:      MYSELF for now; switch the *deployment* to your domain
 *                when you want to demo it inside your Workspace org.
 *                ANYONE is the "public" bridge -- not crossed yet.
 */

function doGet() {
  return HtmlService.createTemplateFromFile('Index')
    .evaluate()
    .setTitle('GAS Auditor — Inventory Dashboard')
    .addMetaTag('viewport', 'width=device-width, initial-scale=1')
    .setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL);
}

/** Lets Index.html pull in Stylesheet.html / JavaScript.html as includes. */
function include(filename) {
  return HtmlService.createHtmlOutputFromFile(filename).getContent();
}
