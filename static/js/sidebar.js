/**
 * Sidebar Navigation - Mobile drawer toggle
 * Replaces mobile-menu.js for the sidebar layout
 */
document.addEventListener('DOMContentLoaded', function() {
  var sidebar = document.getElementById('sidebar');
  var overlay = document.getElementById('sidebar-overlay');
  var toggle = document.getElementById('sidebar-toggle');

  if (!sidebar || !overlay || !toggle) return;

  function openSidebar() {
    sidebar.classList.remove('-translate-x-full');
    overlay.classList.remove('hidden');
    toggle.setAttribute('aria-expanded', 'true');
    document.body.style.overflow = 'hidden';
  }

  function closeSidebar() {
    sidebar.classList.add('-translate-x-full');
    overlay.classList.add('hidden');
    toggle.setAttribute('aria-expanded', 'false');
    document.body.style.overflow = '';
  }

  toggle.addEventListener('click', function() {
    var isOpen = toggle.getAttribute('aria-expanded') === 'true';
    if (isOpen) {
      closeSidebar();
    } else {
      openSidebar();
    }
  });

  overlay.addEventListener('click', closeSidebar);

  document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape' && toggle.getAttribute('aria-expanded') === 'true') {
      closeSidebar();
    }
  });

  // Auto-close mobile drawer when resizing to desktop
  var desktopQuery = window.matchMedia('(min-width: 1280px)');
  function handleResize(e) {
    if (e.matches) {
      closeSidebar();
    }
  }
  desktopQuery.addEventListener('change', handleResize);
});
