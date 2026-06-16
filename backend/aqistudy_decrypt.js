/**
 * AQI Study decryption bridge — Node.js
 * Loads the site's actual crypto JS and exposes encrypt/decrypt for Python.
 * Usage: node aqistudy_decrypt.js <operation> <json_args>
 *   encrypt '{"method":"GETDAYDATA","params":{"city":"北京","month":"202401"}}'
 *   decrypt '{"data":"UC9Ddm9B..."}'
 */
const fs = require('fs');
const path = require('path');

// 1. Load the crypto library (de5CQkNmdaJwo.min.js)
const cryptoJs = fs.readFileSync(
    path.join(__dirname, '..', 'aqistudy_crypto.js'), 'utf8'
);

// 2. Load the eval block (from daydata.php)
const evalJs = fs.readFileSync(
    path.join(__dirname, '..', 'aqistudy_eval_4.js'), 'utf8'
);

// Extract the JS content (strip script tags)
const evalContent = evalJs.replace(/<script[^>]*>|<\/script>/g, '').trim();

// 3. Mock browser environment
global.window = global;
global.document = {
    createElement: function() { return {}; },
    getElementsByTagName: function() { return []; },
    addEventListener: function() {},
    documentElement: { style: {} }
};
global.navigator = { userAgent: 'Mozilla/5.0' };
global.localStorage = {
    _data: {},
    getItem: function(k) { return this._data[k] || null; },
    setItem: function(k, v) { this._data[k] = v; },
    removeItem: function(k) { delete this._data[k]; }
};
global.sessionStorage = {
    _data: {},
    getItem: function(k) { return this._data[k] || null; },
    setItem: function(k, v) { this._data[k] = v; }
};

// 4. Execute the crypto library (defines decryption function dqf3PsvG9U)
eval(cryptoJs);

// 5. Execute the eval block (this calls dqf3PsvG9U and evals the result)
// But we need to capture the decrypted code, not execute it
// Override eval temporarily
var _originalEval = eval;
var _captured = '';
global.eval = function(code) {
    if (code.length > 5000) {
        _captured = code;
        // Execute the decrypted code in global scope
        return _originalEval.call(global, code);
    }
    return _originalEval.call(global, code);
};

_originalEval.call(global, evalContent);

// Reset eval
global.eval = _originalEval;

// 6. Now the functions should be defined globally
// Key functions: encrypt_request (the one that calls the API)
// Actually the eval'd code defines:
//   poPBVxzNuafY8Yu(method, params) → encrypted request string
//   dxvERkeEvHbS(data) → decrypted JSON string
//   sSPnfjolBsGjl66hUEw8(method, params, callback, cache_ttl) → full API call with caching
//   getCityList, etc.

// The HTTP request function was obfuscated. Let's find the request encryption function
// from the decrypted code.

// Check which functions are available
var availableFuncs = Object.keys(global).filter(k =>
    typeof global[k] === 'function' && k.length > 5 && !k.startsWith('_')
);

// Find the specific crypto functions
var funcs = {};
for (var key in global) {
    if (typeof global[key] === 'function') {
        funcs[key] = true;
    }
}

// The decrypt function is: dxvERkeEvHbS
// Let's test if it exists
if (typeof global.dxvERkeEvHbS === 'function') {
    // Test decryption
    var testData = 'UC9Ddm9BQXdhLzIrZUFmRzRFc080bjBnRkRpNUV1cTVQU0RhRnBOMDN2bDJPZTNPVU5WWHhKTjM4Yk5DTm5FMm1HeTIvSEN3aXIycTd4T0JESS9kSllKbHd3c1VuVk5uVXNnZFBsR2d5eTcvN2J2VXN4cW9YZkoxNEk5TlhuYldxcmp0aU5XTHRFNHc4M2RoaUp4UHdFS0lsOWtyNEN4ZnA1NjdzRkJ4cHpKU2ZPSzVmdUs3YTNuVzVNRW5rL1RISDBBPT0=';
    try {
        var decrypted = global.dxvERkeEvHbS(testData);
        console.log('DECRYPT_OK:' + decrypted);
    } catch(e) {
        console.log('DECRYPT_ERR:' + e.message);
    }
} else {
    console.log('FUNCTIONS:' + JSON.stringify(Object.keys(funcs).filter(k => k.length > 8)));
}
