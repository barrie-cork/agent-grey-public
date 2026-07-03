/**
 * Vue Router Configuration
 * Defines routes for dual screening SPA
 */

import { createRouter, createWebHistory, type RouteLocationNormalized, type NavigationGuardNext } from 'vue-router';
import { useOrganisationStore } from '../stores/organisation';
import { useAuthStore } from '../stores/auth';

// Lazy-loaded route components for code splitting
const WorkQueue = () => import('../views/WorkQueue.vue');
const ScreeningDecision = () => import('../views/ScreeningDecision.vue');
const ConflictResolution = () => import('../views/ConflictResolution.vue');
const ConflictList = () => import('../views/ConflictList.vue');
const TeamDashboard = () => import('../views/TeamDashboard.vue');
const ComponentShowcase = () => import('../views/ComponentShowcase.vue');

const router = createRouter({
  history: createWebHistory('/screening/'),
  routes: [
    {
      path: '/',
      redirect: (to) => {
        // FIX (Issue #32): Preserve query parameters during redirect
        // When redirecting from / to /work-queue, keep session_id in URL
        return { path: '/work-queue', query: to.query };
      },
    },
    {
      path: '/work-queue',
      name: 'work-queue',
      component: WorkQueue,
      meta: {
        requiresAuth: true,
        title: 'Work Queue',
      },
    },
    {
      path: '/results/:id/screen',
      name: 'screening',
      component: ScreeningDecision,
      meta: {
        requiresAuth: true,
        title: 'Screening Decision',
      },
      props: true,
    },
    {
      path: '/conflicts',
      name: 'conflicts',
      component: ConflictList,
      meta: {
        requiresAuth: true,
        title: 'Discussions Needed',
      },
    },
    {
      path: '/conflicts/:id',
      name: 'conflict-resolution',
      component: ConflictResolution,
      meta: {
        requiresAuth: true,
        title: 'Discussion Resolution',
      },
      props: true,
    },
    {
      path: '/dashboard',
      name: 'dashboard',
      component: TeamDashboard,
      meta: {
        requiresAuth: true,
        title: 'Team Dashboard',
      },
    },
    {
      path: '/component-showcase',
      name: 'component-showcase',
      component: ComponentShowcase,
      meta: {
        requiresAuth: false,
        title: 'Component Showcase',
      },
    },
  ],
});

// Navigation guards
router.beforeEach((to: RouteLocationNormalized, _from: RouteLocationNormalized, next: NavigationGuardNext) => {
  const authStore = useAuthStore();
  const orgStore = useOrganisationStore();

  // Set page title
  if (to.meta.title) {
    document.title = `${to.meta.title} - Agent Grey`;
  }

  // Check authentication
  if (to.meta.requiresAuth && !authStore.isAuthenticated) {
    console.warn('Not authenticated - redirecting to login');
    window.location.href = '/accounts/login/';
    return;
  }

  // CRITICAL: Check organisation context
  if (to.meta.requiresAuth && !orgStore.hasOrganisation) {
    console.warn('No organisation context - redirecting to selection');
    window.location.href = '/organisation/select/';
    return;
  }

  next();
});

export default router;
