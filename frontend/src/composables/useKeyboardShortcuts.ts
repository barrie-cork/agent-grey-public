/**
 * Keyboard shortcuts composable.
 *
 * Registers keypress handlers with a configurable key-action map.
 * Ignores keypresses when focus is inside form elements.
 */

import { onMounted, onUnmounted } from 'vue';

type KeyActionMap = Record<string, () => void>;

export function useKeyboardShortcuts(keyMap: KeyActionMap) {
  function handleKeyPress(event: KeyboardEvent) {
    if (
      event.target instanceof HTMLTextAreaElement ||
      event.target instanceof HTMLInputElement ||
      event.target instanceof HTMLSelectElement
    ) {
      return;
    }

    const key = event.key.toLowerCase();
    const action = keyMap[key];

    if (action) {
      action();
      event.preventDefault();
    }
  }

  onMounted(() => {
    window.addEventListener('keypress', handleKeyPress);
  });

  onUnmounted(() => {
    window.removeEventListener('keypress', handleKeyPress);
  });
}
