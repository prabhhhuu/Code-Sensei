// Theme persistence
(function () {
    var saved = localStorage.getItem('theme') || 'dark';
    if (saved === 'light') document.body.classList.add('light-mode');
})();
