// BOBO OS — Firefox Privacy & BOBO OS Branding Configuration (Phase 8.2)
// E:\BOBO-OS\apps\browser\user.js
//
// Applied to Firefox profile via user.js mechanism.
// These settings override the defaults in prefs.js.

// ── Telemetry: disable all ────────────────────────────────────────────────────
user_pref("toolkit.telemetry.enabled",                    false);
user_pref("toolkit.telemetry.unified",                    false);
user_pref("toolkit.telemetry.server",                     "");
user_pref("datareporting.healthreport.uploadEnabled",     false);
user_pref("datareporting.policy.dataSubmissionEnabled",   false);
user_pref("browser.ping-centre.telemetry",                false);
user_pref("browser.newtabpage.activity-stream.feeds.telemetry", false);
user_pref("browser.newtabpage.activity-stream.telemetry", false);

// ── Pocket: disable ─────────────────────────────────────────────────────────
user_pref("extensions.pocket.enabled",                    false);
user_pref("browser.newtabpage.activity-stream.feeds.section.topstories", false);
user_pref("browser.newtabpage.activity-stream.showSponsored",             false);
user_pref("browser.newtabpage.activity-stream.showSponsoredTopSites",     false);

// ── Default search engine: DuckDuckGo ────────────────────────────────────────
user_pref("browser.search.defaultenginename",             "DuckDuckGo");
user_pref("browser.search.selectedEngine",                "DuckDuckGo");
user_pref("browser.urlbar.suggest.searches",              true);

// ── DNS over HTTPS (Cloudflare, respects privacy) ────────────────────────────
user_pref("network.trr.mode",                             2);
user_pref("network.trr.uri",                              "https://cloudflare-dns.com/dns-query");

// ── Privacy: tracking protection ─────────────────────────────────────────────
user_pref("privacy.trackingprotection.enabled",           true);
user_pref("privacy.trackingprotection.socialtracking.enabled", true);
user_pref("privacy.trackingprotection.fingerprinting.enabled", true);
user_pref("privacy.trackingprotection.cryptomining.enabled",   true);
user_pref("network.cookie.cookieBehavior",                1);   // block 3rd party cookies
user_pref("privacy.firstparty.isolate",                   true);
user_pref("privacy.resistFingerprinting",                 true);

// ── WebRTC leak prevention ────────────────────────────────────────────────────
user_pref("media.peerconnection.enabled",                 false);
user_pref("media.peerconnection.ice.no_host",             true);

// ── HTTPS-only mode ───────────────────────────────────────────────────────────
user_pref("dom.security.https_only_mode",                 true);
user_pref("dom.security.https_only_mode_ever_enabled",    true);

// ── Disable sponsored content on New Tab page ─────────────────────────────────
user_pref("browser.newtabpage.activity-stream.feeds.snippets", false);
user_pref("browser.newtabpage.activity-stream.asrouter.userprefs.cfr.addons",    false);
user_pref("browser.newtabpage.activity-stream.asrouter.userprefs.cfr.features",  false);

// ── Performance: hardware acceleration ────────────────────────────────────────
user_pref("gfx.webrender.all",                            true);
user_pref("media.ffmpeg.vaapi.enabled",                   true);   // VA-API video decode
user_pref("media.hardware-video-decoding.enabled",        true);
user_pref("layers.acceleration.force-enabled",            true);

// ── UI: match BOBO OS style ───────────────────────────────────────────────────
user_pref("browser.theme.content-theme",                  0);      // dark content
user_pref("widget.use-xdg-desktop-portal",                true);   // use GTK file dialog
user_pref("browser.display.use_system_colors",            false);

// ── Downloads: always ask where to save ──────────────────────────────────────
user_pref("browser.download.useDownloadDir",              false);
user_pref("browser.download.always_ask_before_handling_new_types", true);

// ── Startup: restore previous session ────────────────────────────────────────
user_pref("browser.startup.page",                         3);      // 3 = restore previous
user_pref("browser.sessionstore.resume_from_crash",       true);

// ── Extensions: auto-install uBlock Origin and Privacy Badger ────────────────
// (Actual installation is handled by the installer via policies.json)
user_pref("extensions.autoDisableScopes",                 0);

// ── Disable Firefox Accounts / Sync (BOBO OS uses NovaSync instead) ──────────
user_pref("identity.fxaccounts.enabled",                  false);
