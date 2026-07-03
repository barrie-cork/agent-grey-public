/**
 * Mobile Menu Toggle - Vanilla JS replacement for Bootstrap collapse
 * @source Phase 06 Django Base Template Migration
 */
document.addEventListener('DOMContentLoaded', function() {
  const mobileMenuButton = document.getElementById('mobile-menu-button');
  const mobileMenu = document.getElementById('mobile-menu');
  const menuIcon = document.getElementById('menu-icon');
  const closeIcon = document.getElementById('close-icon');

  if (mobileMenuButton && mobileMenu && menuIcon && closeIcon) {
    mobileMenuButton.addEventListener('click', function() {
      const isExpanded = mobileMenuButton.getAttribute('aria-expanded') === 'true';

      // Toggle aria-expanded
      mobileMenuButton.setAttribute('aria-expanded', !isExpanded);

      // Toggle menu visibility
      mobileMenu.classList.toggle('hidden');

      // Toggle icons
      menuIcon.classList.toggle('hidden');
      menuIcon.classList.toggle('block');
      closeIcon.classList.toggle('hidden');
      closeIcon.classList.toggle('block');
    });

    // Close menu when clicking outside
    document.addEventListener('click', function(event) {
      if (!mobileMenuButton.contains(event.target) && !mobileMenu.contains(event.target)) {
        mobileMenu.classList.add('hidden');
        mobileMenuButton.setAttribute('aria-expanded', 'false');
        menuIcon.classList.remove('hidden');
        menuIcon.classList.add('block');
        closeIcon.classList.add('hidden');
        closeIcon.classList.remove('block');
      }
    });
  }
});
