/**
 * Timer composable.
 *
 * Provides elapsed-time tracking with start/stop controls
 * and a formatted mm:ss display string.
 */

import { ref, computed, onUnmounted } from 'vue';

export function useTimer() {
  const startTime = ref<number>(Date.now());
  const elapsedSeconds = ref(0);
  const timerInterval = ref<number | null>(null);

  const formattedTime = computed(() => {
    const minutes = Math.floor(elapsedSeconds.value / 60);
    const seconds = elapsedSeconds.value % 60;
    return `${minutes}:${seconds.toString().padStart(2, '0')}`;
  });

  function startTimer() {
    startTime.value = Date.now();
    elapsedSeconds.value = 0;

    timerInterval.value = window.setInterval(() => {
      elapsedSeconds.value = Math.floor((Date.now() - startTime.value) / 1000);
    }, 1000);
  }

  function stopTimer() {
    if (timerInterval.value !== null) {
      clearInterval(timerInterval.value);
      timerInterval.value = null;
    }
  }

  onUnmounted(() => {
    stopTimer();
  });

  return {
    elapsedSeconds,
    formattedTime,
    startTimer,
    stopTimer,
  };
}
