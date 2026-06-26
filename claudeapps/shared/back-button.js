(function () {
  function init() {
    const style = document.createElement('style');
    style.textContent = `
      #claudeapps-back {
        position: fixed;
        top: 16px;
        left: 16px;
        z-index: 99999;
        display: flex;
        align-items: center;
        justify-content: center;
        width: 36px;
        height: 36px;
        border-radius: 8px;
        background: rgba(0,0,0,0.35);
        backdrop-filter: blur(6px);
        text-decoration: none;
        opacity: 0.6;
        transition: opacity 0.15s, background 0.15s;
      }
      #claudeapps-back:hover {
        opacity: 1;
        background: rgba(0,0,0,0.55);
      }
      #claudeapps-back svg {
        display: block;
      }
    `;
    document.head.appendChild(style);

    const a = document.createElement('a');
    a.id = 'claudeapps-back';
    a.href = '/claudeapps/';
    a.title = 'Zurück zur Übersicht';
    a.innerHTML = `<svg width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M10 3L5 8L10 13" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
    </svg>`;

    document.body.appendChild(a);
  }

  if (document.body) {
    init();
  } else {
    document.addEventListener('DOMContentLoaded', init);
  }
})();
