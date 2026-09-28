var editor = CodeMirror(document.getElementById('codeEditor'), {
    mode:        'python',
    theme:       'dracula',
    lineNumbers: true,
    tabSize:     4,
    indentWithTabs: false,
    autofocus:   true,
    lineWrapping: true,
});

var modeMap = {
    python:     'python',
    javascript: 'javascript',
    java:       'text/x-java',
    c:          'text/x-csrc',
    cpp:        'text/x-c++src',
};

document.getElementById('language').addEventListener('change', function () {
    editor.setOption('mode', modeMap[this.value] || 'python');
});

document.getElementById('clearBtn').addEventListener('click', function () {
    editor.setValue('');
    document.getElementById('outputContent').innerHTML =
        '<p class="output-placeholder">Submit your code to get AI feedback.</p>';
});

document.getElementById('analyzeBtn').addEventListener('click', function () {
    var btn     = this;
    var code    = editor.getValue().trim();
    var lang    = document.getElementById('language').value;
    var mode    = document.getElementById('mode').value;
    var output  = document.getElementById('outputContent');

    if (!code) {
        output.innerHTML = '<p style="color:#f87171">Please write some code first.</p>';
        return;
    }

    btn.disabled    = true;
    btn.textContent = 'Analysing…';
    output.innerHTML = '<p class="output-placeholder">Thinking…</p>';

    fetch('/api/analyse', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ code: code, language: lang, mode: mode }),
    })
    .then(function (r) {
        if (r.status === 401) {
            output.innerHTML = '<p style="color:#f87171">Please log in to analyze code.</p>';
            return;
        }
        return r.json();
    })
    .then(function (data) {
        if (data) {
            output.innerHTML = data.result
                ? '<p>' + data.result.replace(/\n/g, '<br>') + '</p>'
                : '<p style="color:#f87171">No response received.</p>';
        }
    })
    .catch(function (err) {
        output.innerHTML = '<p style="color:#f87171">Error: ' + err.message + '</p>';
    })
    .finally(function () {
        btn.disabled    = false;
        btn.textContent = '⚡ Analyse';
    });
});

