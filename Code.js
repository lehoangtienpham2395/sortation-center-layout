/**
 * Production Architecture Refactor & Performance Optimization
 * Warehouse Digital Twin - Google Apps Script
 */

// ─── PRODUCTION MONITORING & LOGGER CONFIGURATION ───
const DEBUG = false; // Set to true in development, false in production

var stats = {
  sheetsRead: 0,
  sheetsWrite: 0,
  cacheHit: 0,
  cacheMiss: 0,
  startTime: 0
};

function startTracking() {
  stats.sheetsRead = 0;
  stats.sheetsWrite = 0;
  stats.cacheHit = 0;
  stats.cacheMiss = 0;
  stats.startTime = Date.now();
}

function logDebug(tag, msg) {
  if (DEBUG || tag === "ERROR") {
    Logger.log("[" + tag + "] " + msg);
  }
}

function logStats(tag, actionName) {
  var duration = Date.now() - stats.startTime;
  logDebug(tag, actionName + " completed in " + duration + "ms. [Stats: SheetsRead=" + stats.sheetsRead + ", SheetsWrite=" + stats.sheetsWrite + ", CacheHit=" + stats.cacheHit + ", CacheMiss=" + stats.cacheMiss + "]");
}

/**
 * Serves the HTML frontend and checks if database initialization is needed.
 */
function doGet(e) {
  startTracking();
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  stats.sheetsRead++;
  
  // Phase 15: Run initialization only if User sheet is missing
  if (ss && !ss.getSheetByName("User")) {
    initializeDatabase(ss);
  }
  
  var output = HtmlService.createHtmlOutputFromFile('Index');
  output.setTitle("J&T Cargo HCM HUB - Warehouse Digital Twin Platform")
        .setSandboxMode(HtmlService.SandboxMode.IFRAME)
        .setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL)
        .addMetaTag('viewport', 'width=device-width, initial-scale=1, shrink-to-fit=no');
        
  logStats("PERF", "doGet");
  return output;
}

/**
 * Initializes the database sheets (User, Role, Permission) if they don't exist.
 */
function initializeDatabase(ss) {
  try {
    logDebug("PERF", "Initializing database sheets...");
    if (!ss) ss = SpreadsheetApp.getActiveSpreadsheet();

    // 1. Role Sheet
    var roleSheet = ss.getSheetByName("Role");
    if (!roleSheet) {
      roleSheet = ss.insertSheet("Role");
      roleSheet.appendRow(["RoleID", "RoleName", "Description"]);
      roleSheet.getRange(1, 1, 1, 3).setFontWeight("bold").setBackground("#d9ead3");
      roleSheet.appendRow(["OWNER", "Chu so huu", "Toan quyen cau truc kho va camera"]);
      roleSheet.appendRow(["ADMIN", "Quan tri vien", "Quan tri thiet bi camera va chinh sua thuoc tinh"]);
      roleSheet.appendRow(["USER", "Nhan vien van hanh", "Chi xem camera va ban do kho"]);
      stats.sheetsWrite += 4;
    }

    // 2. Permission Sheet
    var permSheet = ss.getSheetByName("Permission");
    if (!permSheet) {
      permSheet = ss.insertSheet("Permission");
      permSheet.appendRow(["RoleID", "Permission"]);
      permSheet.getRange(1, 1, 1, 2).setFontWeight("bold").setBackground("#d9ead3");
      stats.sheetsWrite += 2;
      
      var defaultPerms = [
        ["OWNER", "warehouse.edit"],
        ["OWNER", "warehouse.delete"],
        ["OWNER", "camera.edit"],
        ["OWNER", "camera.rotate"],
        ["OWNER", "camera.delete"],
        ["OWNER", "config.save"],
        ["OWNER", "config.import"],
        ["OWNER", "config.export"],
        ["OWNER", "history.undo"],
        ["OWNER", "history.redo"],
        
        ["ADMIN", "camera.rotate"],
        ["ADMIN", "camera.fov"],
        ["ADMIN", "camera.range"],
        ["ADMIN", "camera.property"],
        
        ["USER", "warehouse.view"],
        ["USER", "camera.view"],
        ["USER", "zoom"],
        ["USER", "pan"]
      ];
      for (var i = 0; i < defaultPerms.length; i++) {
        permSheet.appendRow(defaultPerms[i]);
        stats.sheetsWrite++;
      }
    }

    // 3. User Sheet
    var userSheet = ss.getSheetByName("User");
    if (!userSheet) {
      userSheet = ss.insertSheet("User");
      userSheet.appendRow(["UserID", "Username", "Password", "FullName", "Email", "RoleID", "Status"]);
      userSheet.getRange(1, 1, 1, 7).setFontWeight("bold").setBackground("#d9ead3");
      userSheet.appendRow(["U001", "owner",   "owner123",  "Hoang Owner",    "owner@jtcargo.vn",  "OWNER", "Active"]);
      userSheet.appendRow(["U002", "admin01", "admin123",  "Minh Admin",     "admin@jtcargo.vn",  "ADMIN", "Active"]);
      userSheet.appendRow(["U003", "user01",  "user123",   "User Van Hanh",  "user@jtcargo.vn",   "USER",  "Active"]);
      stats.sheetsWrite += 5;
    }
  } catch (error) {
    logDebug("ERROR", "Error initializing database: " + error.toString());
  }
}

/**
 * Internal helper to load camera layout configuration.
 */
function _loadCameraLayout(ss) {
  try {
    var sheet = ss.getSheetByName("CameraLayout");
    stats.sheetsRead++;
    if (!sheet) return [];
    
    var lastRow = sheet.getLastRow();
    if (lastRow <= 1) return [];
    
    // Phase 3: Limit range read to required columns only (Columns A to H -> 8 columns)
    var data = sheet.getRange(1, 1, lastRow, 8).getValues();
    stats.sheetsRead++;
    
    var cameras = [];
    var headers = data[0];
    
    var colId     = headers.indexOf("Camera ID");     if (colId === -1)     colId = 0;
    var colName   = headers.indexOf("Camera Name");   if (colName === -1)   colName = 1;
    var colX      = headers.indexOf("X");             if (colX === -1)      colX = 2;
    var colY      = headers.indexOf("Y");             if (colY === -1)      colY = 3;
    var colAngle  = headers.indexOf("Angle");         if (colAngle === -1)  colAngle = 4;
    var colSpread = headers.indexOf("Spread");        if (colSpread === -1) colSpread = 5;
    var colRange  = headers.indexOf("Range");         if (colRange === -1)  colRange = 6;
    var colPlaced = headers.indexOf("Placed");        if (colPlaced === -1) colPlaced = 7;
    
    for (var i = 1; i < data.length; i++) {
      var row = data[i];
      if (!row[colId]) continue; // Skip empty rows
      cameras.push({
        id:     String(row[colId]),
        name:   String(row[colName] || ""),
        x:      row[colX]      !== "" ? Number(row[colX])      : 0,
        y:      row[colY]      !== "" ? Number(row[colY])      : 0,
        angle:  row[colAngle]  !== "" ? Number(row[colAngle])  : 0,
        spread: row[colSpread] !== "" ? Number(row[colSpread]) : 60,
        range:  row[colRange]  !== "" ? Number(row[colRange])  : 80,
        placed: row[colPlaced] === true || String(row[colPlaced]).toLowerCase() === "true"
      });
    }
    
    return cameras;
  } catch (error) {
    logDebug("ERROR", "Error in _loadCameraLayout: " + error.toString());
    return [];
  }
}

/**
 * Internal helper to load bưu cục names.
 */
function _loadBieuCucNames(ss) {
  try {
    var sheet = ss.getSheetByName("Config");
    stats.sheetsRead++;
    if (!sheet) return {};
    
    var lastRow = sheet.getLastRow();
    if (lastRow <= 1) return {};
    
    // Only fetch zone, areaid, buucuc (first 3 columns)
    var data = sheet.getRange(1, 1, lastRow, 3).getValues();
    stats.sheetsRead++;
    
    var mapping = {};
    var headers = data[0];
    var colZone   = headers.indexOf("Zone");     if (colZone === -1)   colZone = 0;
    var colAreaId = headers.indexOf("AreaID");   if (colAreaId === -1) colAreaId = 1;
    var colName   = headers.indexOf("Buu cuc");  if (colName === -1)   colName = 2;
    
    for (var i = 1; i < data.length; i++) {
      var row = data[i];
      var zone   = String(row[colZone]   || "").trim().toUpperCase();
      var areaId = String(row[colAreaId] || "").trim().toUpperCase();
      var name   = String(row[colName]   || "").trim();
      if (zone && areaId) {
        mapping[zone + "_" + areaId] = name;
      }
    }
    return mapping;
  } catch (error) {
    logDebug("ERROR", "Error in _loadBieuCucNames: " + error.toString());
    return {};
  }
}

/**
 * Authenticates user - always queries User sheet directly (No Cache to prevent stale profiles)
 */
function verifyCredentials(username, password) {
  startTracking();
  try {
    logDebug("AUTH", "Verifying credentials for username: '" + username + "'");
    var ss = SpreadsheetApp.getActiveSpreadsheet();
    stats.sheetsRead++;
    if (!ss) return { success: false, error: "DatabaseConnectionError" };
    
    var userSheet = ss.getSheetByName("User");
    stats.sheetsRead++;
    if (!userSheet) {
      initializeDatabase(ss);
      userSheet = ss.getSheetByName("User");
      stats.sheetsRead++;
      if (!userSheet) return { success: false, error: "UserSheetNotFound" };
    }

    var lastRow = userSheet.getLastRow();
    // Only load columns A to G (7 columns) to optimize memory
    var data = userSheet.getRange(1, 1, lastRow, 7).getValues();
    stats.sheetsRead++;
    
    var rowIdx = -1;
    for (var i = 1; i < data.length; i++) {
      var sheetUser = String(data[i][1]).trim();
      if (sheetUser.toLowerCase() === String(username).trim().toLowerCase()) {
        rowIdx = i;
        break;
      }
    }
    
    if (rowIdx === -1) {
      logDebug("AUTH", "Username not found: '" + username + "'");
      return { success: false, error: "InvalidCredentials" };
    }
    
    var row = data[rowIdx];
    var dbPassword = String(row[2]).trim();
    var fullName   = String(row[3]);
    var roleId     = String(row[5]);
    var status     = String(row[6]).trim();
    
    if (status !== "Active") {
      logDebug("AUTH", "Account is not Active: '" + username + "'");
      return { success: false, error: "AccountDisabled" };
    }
    
    if (String(password).trim() !== dbPassword) {
      logDebug("AUTH", "Incorrect password for '" + username + "'");
      return { success: false, error: "InvalidCredentials" };
    }
    
    // Load permissions
    var permissions = [];
    var permSheet = ss.getSheetByName("Permission");
    stats.sheetsRead++;
    if (permSheet) {
      var permLastRow = permSheet.getLastRow();
      var permData = permSheet.getRange(1, 1, permLastRow, 2).getValues();
      stats.sheetsRead++;
      for (var j = 1; j < permData.length; j++) {
        if (String(permData[j][0]) === roleId) {
          permissions.push(String(permData[j][1]));
        }
      }
    }
    
    var sessionToken = "session_" + Utilities.getUuid().replace(/-/g, "");
    var sessionData = {
      userId: String(row[0]),
      username: String(row[1]),
      fullName: fullName,
      roleId: roleId,
      permissions: permissions,
      token: sessionToken,
      expiredTime: Date.now() + 30 * 60 * 1000
    };
    
    CacheService.getScriptCache().put(sessionToken, JSON.stringify(sessionData), 1800);
    
    // Persistent Session Backup Strategy
    try {
      PropertiesService.getScriptProperties().setProperty(sessionToken, JSON.stringify(sessionData));
      // Run asynchronous-like cleanup of old sessions
      _cleanupExpiredSessions();
    } catch (e) {
      logDebug("ERROR", "Failed to save session to PropertiesService: " + e.toString());
    }
    
    logDebug("AUTH", "Login Successful. Token: " + sessionToken);
    logStats("PERF", "verifyCredentials");
    
    // Phase 5: Return quickly without loading layout cameras/chute names in the login flow.
    return {
      success: true,
      token: sessionToken,
      username: String(row[1]),
      fullName: fullName,
      roleId: roleId,
      permissions: permissions
    };

  } catch (error) {
    logDebug("ERROR", "verifyCredentials Error: " + error.toString());
    return { success: false, error: "InternalError" };
  }
}

/**
 * Server-side Session validation.
 */
function validateSession(token) {
  try {
    if (!token) return { success: false, error: "SessionMissing" };
    var cacheVal = CacheService.getScriptCache().get(token);
    
    if (!cacheVal) {
      stats.cacheMiss++;
      // Check PropertiesService backup
      cacheVal = PropertiesService.getScriptProperties().getProperty(token);
      if (!cacheVal) {
        return { success: false, error: "SessionExpired" };
      }
      // Restore to CacheService
      CacheService.getScriptCache().put(token, cacheVal, 1800);
    } else {
      stats.cacheHit++;
    }
    
    var session = JSON.parse(cacheVal);
    var now = Date.now();
    if (session.expiredTime && now > session.expiredTime) {
      // Session has truly expired
      PropertiesService.getScriptProperties().deleteProperty(token);
      CacheService.getScriptCache().remove(token);
      return { success: false, error: "SessionExpired" };
    }
    
    // Extend expiration by 30 minutes
    session.expiredTime = now + 30 * 60 * 1000;
    session.token = token;
    var updatedSessionStr = JSON.stringify(session);
    CacheService.getScriptCache().put(token, updatedSessionStr, 1800);
    PropertiesService.getScriptProperties().setProperty(token, updatedSessionStr);
    
    return { success: true, session: session };
  } catch (error) {
    return { success: false, error: "SessionVerificationFailed" };
  }
}

/**
 * Cleanup function to remove old expired sessions from PropertiesService.
 */
function _cleanupExpiredSessions() {
  try {
    var props = PropertiesService.getScriptProperties();
    var keys = props.getKeys();
    var now = Date.now();
    for (var i = 0; i < keys.length; i++) {
      var key = keys[i];
      if (key.indexOf("session_") === 0) {
        var val = props.getProperty(key);
        if (val) {
          try {
            var session = JSON.parse(val);
            if (session.expiredTime && now > session.expiredTime) {
              props.deleteProperty(key);
            }
          } catch(e) {
            props.deleteProperty(key);
          }
        }
      }
    }
  } catch(e) {}
}

/**
 * Version Markers checking for Auto-Login.
 */
function validateAndLoadSession(token) {
  startTracking();
  try {
    var sessionCheck = validateSession(token);
    if (!sessionCheck.success) {
      return { success: false, error: "SessionExpired" };
    }
    
    // Return session details with server-side versions for cache check on client side
    var props = PropertiesService.getScriptProperties().getProperties();
    var versions = {
      cams_version: props.cams_version || "0",
      config_version: props.config_version || "0"
    };
    
    logStats("PERF", "validateAndLoadSession");
    return {
      success: true,
      session: sessionCheck.session,
      versions: versions
    };
  } catch (error) {
    logDebug("ERROR", "validateAndLoadSession error: " + error.toString());
    return { success: false, error: "InternalError" };
  }
}

/**
 * Checks server side cache and versions before reading Spreadsheet layout.
 */
function loadCameraLayout(sessionToken) {
  startTracking();
  try {
    var sessionCheck = validateSession(sessionToken);
    if (!sessionCheck.success) {
      return { error: "SessionExpired" };
    }
    
    var props = PropertiesService.getScriptProperties().getProperties();
    var serverVer = props.cams_version || "0";
    
    // Check Cache Service
    var cache = CacheService.getScriptCache();
    var cachedVer = cache.get("cams_version");
    
    if (cachedVer === serverVer) {
      var cachedData = cache.get("cams_layout_data");
      if (cachedData) {
        stats.cacheHit += 2;
        logStats("CACHE", "loadCameraLayout (Cache Hit)");
        return JSON.parse(cachedData);
      }
    }
    
    stats.cacheMiss++;
    // Cache Miss -> Read Sheets
    var ss = SpreadsheetApp.getActiveSpreadsheet();
    stats.sheetsRead++;
    if (!ss) return [];
    
    var cameras = _loadCameraLayout(ss);
    
    // Safe Cache Strategy: Limit size to <95KB to prevent Google quotas error
    try {
      var jsonStr = JSON.stringify(cameras);
      if (jsonStr.length < 95000) {
        cache.put("cams_layout_data", jsonStr, 1800);
        cache.put("cams_version", serverVer, 1800);
        logDebug("CACHE", "Saved CameraLayout to Cache Service. size: " + jsonStr.length + " bytes");
      } else {
        logDebug("CACHE", "CameraLayout exceeds cache threshold. size: " + jsonStr.length + " bytes. Skipping Cache.");
      }
    } catch (e) {
      logDebug("ERROR", "SafeCache failed: " + e.toString());
    }
    
    logStats("PERF", "loadCameraLayout (Sheets Read)");
    return cameras;
  } catch (error) {
    logDebug("ERROR", "loadCameraLayout failed: " + error.toString());
    return [];
  }
}

/**
 * Saves the camera layout configuration. Uses LockService and Atomic Overwrite.
 */
function saveCameraLayout(cameraDataJson, sessionToken) {
  startTracking();
  
  // 1. Lock Service to prevent write conflicts
  var lock = LockService.getScriptLock();
  try {
    lock.waitLock(10000); // 10s wait threshold
  } catch (e) {
    logDebug("SAVE", "Lock timeout conflict.");
    return { success: false, error: "ConcurrencyConflict" };
  }
  
  var backupRows = [];
  var sheet = null;
  var headers = ["Camera ID", "Camera Name", "X", "Y", "Angle", "Spread", "Range", "Placed"];
  
  try {
    var sessionCheck = validateSession(sessionToken);
    if (!sessionCheck.success) {
      lock.releaseLock();
      return { success: false, error: "SessionExpired" };
    }
    
    var permissions = sessionCheck.session.permissions;
    if (permissions.indexOf("config.save") === -1 && sessionCheck.session.roleId !== "OWNER") {
      lock.releaseLock();
      return { success: false, error: "AccessDenied" };
    }

    var cameras = JSON.parse(cameraDataJson);
    if (!Array.isArray(cameras)) {
      throw new Error("Invalid cameras array.");
    }
    
    var ss = SpreadsheetApp.getActiveSpreadsheet();
    stats.sheetsRead++;
    if (!ss) throw new Error("SpreadsheetNotFound");
    
    sheet = ss.getSheetByName("CameraLayout");
    stats.sheetsRead++;
    if (!sheet) {
      sheet = ss.insertSheet("CameraLayout");
      stats.sheetsWrite++;
    }
    
    // Invalidate Server Cache immediately before write
    var cache = CacheService.getScriptCache();
    cache.remove("cams_layout_data");
    cache.remove("cams_version");
    
    // Backup Strategy: Read old layout for restoration in case of failure
    var oldLastRow = sheet.getLastRow();
    if (oldLastRow >= 1) {
      backupRows = sheet.getRange(1, 1, oldLastRow, headers.length).getValues();
      stats.sheetsRead++;
    }
    
    var rows = [headers];
    for (var i = 0; i < cameras.length; i++) {
      var cam = cameras[i];
      rows.push([
        cam.id || "",
        cam.name || "",
        cam.x      !== undefined ? Number(cam.x)      : "",
        cam.y      !== undefined ? Number(cam.y)      : "",
        cam.angle  !== undefined ? Number(cam.angle)  : "",
        cam.spread !== undefined ? Number(cam.spread) : "",
        cam.range  !== undefined ? Number(cam.range)  : "",
        cam.placed === true
      ]);
    }
    
    // Safe Save Strategy: Overwrite starting at row 1
    sheet.getRange(1, 1, rows.length, headers.length).setValues(rows);
    stats.sheetsWrite++;
    
    var currentLastRow = sheet.getLastRow();
    if (currentLastRow > rows.length) {
      sheet.deleteRows(rows.length + 1, currentLastRow - rows.length);
      stats.sheetsWrite++;
    }
    
    // Flush to commit sheet writes before verifying
    SpreadsheetApp.flush();
    
    // Verify Spreadsheet Write
    var verifyData = sheet.getRange(1, 1, rows.length, headers.length).getValues();
    stats.sheetsRead++;
    
    // Helper function to normalize values for comparison
    var normalizeVal = function(val) {
      if (val === null || val === undefined) return "";
      var s = String(val).trim().toLowerCase();
      if (s === "0.0" || s === "0") return "0";
      if (s === "false") return "false";
      if (s === "true") return "true";
      return s;
    };

    var cleanNumber = function(val) {
      if (val === "" || val === null || val === undefined) return NaN;
      // Replace comma decimal separators with dots
      var s = String(val).trim().replace(",", ".");
      return Number(s);
    };

    var isValEqual = function(w, v) {
      var normW = normalizeVal(w);
      var normV = normalizeVal(v);
      if (normW === normV) return true;
      
      // If both are numeric, compare them numerically with a float tolerance
      var numW = cleanNumber(w);
      var numV = cleanNumber(v);
      if (!isNaN(numW) && !isNaN(numV)) {
        return Math.abs(numW - numV) < 0.1;
      }
      
      // Treat empty cells and 0 as equivalent
      if ((normW === "" || normW === "0") && (normV === "" || normV === "0")) {
        return true;
      }
      
      return false;
    };

    var matches = true;
    var mismatchReason = "";
    if (verifyData.length !== rows.length) {
      matches = false;
      mismatchReason = "Row count mismatch: Written " + rows.length + ", Verify " + verifyData.length;
    } else {
      for (var r = 0; r < rows.length; r++) {
        for (var c = 0; c < headers.length; c++) {
          var w = rows[r][c];
          var v = verifyData[r][c];
          if (!isValEqual(w, v)) {
            matches = false;
            mismatchReason = "Mismatch at row " + r + " (Cam: " + (rows[r][0] || "Header") + "), col " + c + " (" + headers[c] + "). Written: '" + w + "', Verify: '" + v + "'";
            break;
          }
        }
        if (!matches) break;
      }
    }
    
    if (!matches) {
      throw new Error("VerificationFailed: " + mismatchReason);
    }
    
    // Increase Version in PropertiesService
    var newVer = String(Date.now());
    PropertiesService.getScriptProperties().setProperty("cams_version", newVer);
    
    // Refresh Server Cache
    var cleanJsonStr = JSON.stringify(cameras);
    if (cleanJsonStr.length < 95000) {
      cache.put("cams_layout_data", cleanJsonStr, 1800);
      cache.put("cams_version", newVer, 1800);
    }
    
    lock.releaseLock();
    logStats("SAVE", "saveCameraLayout");
    return { success: true, count: cameras.length, version: newVer };
    
  } catch (error) {
    logDebug("ERROR", "saveCameraLayout failed, triggering restore... Error: " + error.toString());
    
    // Restore Backup Strategy
    if (backupRows && backupRows.length > 0 && sheet) {
      try {
        sheet.getRange(1, 1, backupRows.length, headers.length).setValues(backupRows);
        var restoredLastRow = sheet.getLastRow();
        if (restoredLastRow > backupRows.length) {
          sheet.deleteRows(backupRows.length + 1, restoredLastRow - backupRows.length);
        }
        SpreadsheetApp.flush();
        logDebug("SAVE", "Successfully restored layout backup.");
      } catch (restoreErr) {
        logDebug("ERROR", "Failed to restore layout backup: " + restoreErr.toString());
      }
    }
    
    lock.releaseLock();
    return { success: false, error: error.toString() };
  }
}

/**
 * Loads both versions and chute names (cached for 5 seconds) in a single request.
 */
function loadInitialConfig() {
  startTracking();
  try {
    var props = PropertiesService.getScriptProperties().getProperties();
    var serverCamsVer = props.cams_version || "0";
    var serverConfigVer = props.config_version || "0";
    
    var cache = CacheService.getScriptCache();
    var cachedData = cache.get("bieucuc_names_data_v2");
    var mapping = {};
    
    if (cachedData) {
      stats.cacheHit++;
      mapping = JSON.parse(cachedData);
    } else {
      stats.cacheMiss++;
      var ss = SpreadsheetApp.getActiveSpreadsheet();
      if (ss) {
        mapping = _loadBieuCucNames(ss);
        try {
          var jsonStr = JSON.stringify(mapping);
          if (jsonStr.length < 95000) {
            // Cache for 5 seconds to throttle concurrent requests
            cache.put("bieucuc_names_data_v2", jsonStr, 5);
          }
        } catch (e) {
          logDebug("ERROR", "Short cache write failed: " + e.toString());
        }
      }
    }
    
    return {
      cams_version: serverCamsVer,
      config_version: serverConfigVer,
      chuteNames: mapping
    };
  } catch (error) {
    logDebug("ERROR", "loadInitialConfig failed: " + error.toString());
    return { cams_version: "0", config_version: "0", chuteNames: {} };
  }
}

/**
 * Loads the bưu cục names from the "Config" sheet with ScriptCache validation.
 */
function loadBieuCucNames() {
  startTracking();
  try {
    var props = PropertiesService.getScriptProperties().getProperties();
    var serverVer = props.config_version || "0";
    
    var cache = CacheService.getScriptCache();
    var cachedVer = cache.get("config_version");
    
    if (cachedVer === serverVer) {
      var cachedData = cache.get("bieucuc_names_data");
      if (cachedData) {
        stats.cacheHit += 2;
        logStats("CACHE", "loadBieuCucNames (Cache Hit)");
        return JSON.parse(cachedData);
      }
    }
    
    stats.cacheMiss++;
    var ss = SpreadsheetApp.getActiveSpreadsheet();
    stats.sheetsRead++;
    if (!ss) return {};
    
    var mapping = _loadBieuCucNames(ss);
    
    try {
      var jsonStr = JSON.stringify(mapping);
      if (jsonStr.length < 95000) {
        cache.put("bieucuc_names_data", jsonStr, 1800);
        cache.put("config_version", serverVer, 1800);
      }
    } catch (e) {
      logDebug("ERROR", "Config cache write failed: " + e.toString());
    }
    
    logStats("PERF", "loadBieuCucNames (Sheets Read)");
    return mapping;
  } catch (error) {
    logDebug("ERROR", "loadBieuCucNames failed: " + error.toString());
    return {};
  }
}

/**
 * API to retrieve the current cache versions on demand.
 */
function getVersionMarkers() {
  try {
    var props = PropertiesService.getScriptProperties().getProperties();
    return {
      cams_version: props.cams_version || "0",
      config_version: props.config_version || "0"
    };
  } catch (e) {
    return { cams_version: "0", config_version: "0" };
  }
}

/**
 * UTILITY: Setup function to clear all cache or initialize.
 */
function clearServerCache() {
  try {
    CacheService.getScriptCache().removeAll([
      "cams_layout_data", 
      "cams_version", 
      "bieucuc_names_data", 
      "config_version", 
      "bieucuc_names_data_v2"
    ]);
    PropertiesService.getScriptProperties().setProperties({
      "cams_version": String(Date.now()),
      "config_version": String(Date.now())
    });
    return { success: true, message: "Cleared all caches and reset versions." };
  } catch (e) {
    return { success: false, error: e.toString() };
  }
}

/**
 * Loads the pivoted Outbound data from Google Sheet on demand.
 */
function loadOutboundData() {
  startTracking();
  try {
    var ss = SpreadsheetApp.getActiveSpreadsheet();
    stats.sheetsRead++;
    if (!ss) return [];
    
    var sheet = ss.getSheetByName("Outbound");
    stats.sheetsRead++;
    if (!sheet) return [];
    
    var lastRow = sheet.getLastRow();
    if (lastRow <= 1) return [];
    
    // Headers: Zone, AreaID, Bưu cục, Volume, Dài, Rộng, Sức chứa, Ngày
    var data = sheet.getRange(1, 1, lastRow, 8).getValues();
    stats.sheetsRead++;
    
    var list = [];
    for (var i = 1; i < data.length; i++) {
      var r = data[i];
      if (!r[2]) continue; // Skip if Bưu cục is empty
      list.push({
        zone: String(r[0] || ""),
        areaId: String(r[1] || ""),
        name: String(r[2] || ""),
        volume: Number(r[3]) || 0,
        dai: Number(r[4]) || 8,
        rong: Number(r[5]) || 4,
        capacity: Number(r[6]) || 780,
        date: String(r[7] || "")
      });
    }
    
    logStats("PERF", "loadOutboundData");
    return list;
  } catch (error) {
    logDebug("ERROR", "loadOutboundData failed: " + error.toString());
    return [];
  }
}

/**
 * Loads the pivoted Backlog data from Google Sheet on demand.
 */
function loadBacklogData() {
  startTracking();
  try {
    var ss = SpreadsheetApp.getActiveSpreadsheet();
    stats.sheetsRead++;
    if (!ss) return [];
    
    var sheet = ss.getSheetByName("Backlog");
    stats.sheetsRead++;
    if (!sheet) return [];
    
    var lastRow = sheet.getLastRow();
    if (lastRow <= 1) return [];
    
    // Headers: Zone, AreaID, Bưu cục, Volume, Dài, Rộng, Sức chứa, Ngày
    var data = sheet.getRange(1, 1, lastRow, 8).getValues();
    stats.sheetsRead++;
    
    var list = [];
    for (var i = 1; i < data.length; i++) {
      var r = data[i];
      if (!r[2]) continue;
      list.push({
        zone: String(r[0] || ""),
        areaId: String(r[1] || ""),
        name: String(r[2] || ""),
        volume: Number(r[3]) || 0,
        dai: Number(r[4]) || 8,
        rong: Number(r[5]) || 4,
        capacity: Number(r[6]) || 780,
        date: String(r[7] || "")
      });
    }
    
    logStats("PERF", "loadBacklogData");
    return list;
  } catch (error) {
    logDebug("ERROR", "loadBacklogData failed: " + error.toString());
    return [];
  }
}

/**
 * Loads the pivoted Inventory data from Google Sheet on demand.
 */
function loadInventoryData() {
  startTracking();
  try {
    var ss = SpreadsheetApp.getActiveSpreadsheet();
    stats.sheetsRead++;
    if (!ss) return [];
    
    var sheet = ss.getSheetByName("Inventory");
    stats.sheetsRead++;
    if (!sheet) return [];
    
    var lastRow = sheet.getLastRow();
    if (lastRow <= 1) return [];
    
    // Headers: Zone, AreaID, Bưu cục, Trạng thái, Volume, Dài, Rộng, Sức chứa, Ngày
    var data = sheet.getRange(1, 1, lastRow, 9).getValues();
    stats.sheetsRead++;
    
    var list = [];
    for (var i = 1; i < data.length; i++) {
      var r = data[i];
      if (!r[2]) continue;
      list.push({
        zone: String(r[0] || ""),
        areaId: String(r[1] || ""),
        name: String(r[2] || ""),
        status: String(r[3] || ""),
        volume: Number(r[4]) || 0,
        dai: Number(r[5]) || 8,
        rong: Number(r[6]) || 4,
        capacity: Number(r[7]) || 780,
        date: String(r[8] || "")
      });
    }
    
    logStats("PERF", "loadInventoryData");
    return list;
  } catch (error) {
    logDebug("ERROR", "loadInventoryData failed: " + error.toString());
    return [];
  }
}

/**
 * Triggers on edit to invalidate ONLY the Bưu cục (Config) cache
 * when the Config sheet is modified. Does NOT touch cams_version to
 * avoid unnecessary camera-layout reloads.
 */
function onEdit(e) {
  try {
    if (!e || !e.range) return;
    var sheet = e.range.getSheet();
    var sheetName = sheet ? sheet.getName() : "";

    if (sheetName === "Config") {
      // Only bump config_version so client detects Bưu cục changes
      var newVer = String(Date.now());
      PropertiesService.getScriptProperties().setProperty("config_version", newVer);
      // Evict cached Bưu cục data from CacheService
      CacheService.getScriptCache().removeAll([
        "bieucuc_names_data",
        "config_version",
        "bieucuc_names_data_v2"
      ]);
      logDebug("EDIT", "Config sheet changed. config_version bumped to " + newVer);
    }
  } catch (error) {
    logDebug("ERROR", "onEdit failed: " + error.toString());
  }
}
