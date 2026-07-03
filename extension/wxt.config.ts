import vue from "@vitejs/plugin-vue";
import { defineConfig } from "wxt";

export default defineConfig({
  srcDir: "src",
  manifest: {
    name: "Agent Grey – Source Capture",
    version: "0.1.0",
    description:
      "Capture grey-literature browsing for PRISMA systematic review in Agent Grey.",
    permissions: [
      "storage",
      "tabs",
      "windows",
      "activeTab",
      "scripting",
      "alarms",
    ],
    optional_permissions: ["webNavigation"],
    host_permissions: ["<all_urls>"],
    optional_host_permissions: [],
    action: {
      default_title: "Agent Grey Source Capture",
      default_popup: "popup.html",
    },
  },
  vite: () => ({
    plugins: [vue()],
  }),
});
