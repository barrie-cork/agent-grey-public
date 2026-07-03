import { createApp } from 'vue';
import { createPinia } from 'pinia';
import App from './App.vue';
import router from './router';

// Import custom styles (Tailwind CSS + design tokens)
import './assets/styles/main.css';

// Issue #27 test: This comment forces a new build hash to verify django-vite works

const app = createApp(App);

// Register Pinia store
app.use(createPinia());

// Register Vue Router
app.use(router);

// Mount app
app.mount('#app');
