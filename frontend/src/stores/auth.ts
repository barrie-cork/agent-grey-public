/**
 * Authentication Store
 * Manages user authentication state and session info
 */

import { defineStore } from 'pinia';
import { ref, computed } from 'vue';
import type { User, OrganisationMembership } from '../types';

export const useAuthStore = defineStore('auth', () => {
  // State
  const user = ref<User | null>(null);
  const membership = ref<OrganisationMembership | null>(null);
  const isAuthenticated = ref(false);
  const isLoading = ref(false);

  // Getters
  const userRole = computed(() => membership.value?.role || null);

  const canClaimResults = computed(() => {
    if (!userRole.value) return false;
    return ['REVIEWER', 'LEAD_REVIEWER', 'SENIOR_RESEARCHER', 'INFORMATION_SPECIALIST'].includes(userRole.value);
  });

  const canResolveConflicts = computed(() => {
    if (!userRole.value) return false;
    return ['SENIOR_RESEARCHER', 'INFORMATION_SPECIALIST', 'ARBITRATOR'].includes(userRole.value);
  });

  const canViewOrgDashboard = computed(() => {
    if (!userRole.value) return false;
    return ['SENIOR_RESEARCHER', 'INFORMATION_SPECIALIST'].includes(userRole.value);
  });

  const canInviteUsers = computed(() => {
    return userRole.value === 'INFORMATION_SPECIALIST';
  });

  // Actions
  function setUser(userData: User) {
    user.value = userData;
    isAuthenticated.value = true;
  }

  function setMembership(membershipData: OrganisationMembership) {
    membership.value = membershipData;
  }

  function logout() {
    user.value = null;
    membership.value = null;
    isAuthenticated.value = false;
    // Redirect to Django logout
    window.location.href = '/accounts/logout/';
  }

  function checkAuth() {
    // In a real implementation, this would fetch user data from Django session
    // For now, we assume user data is passed via window object or meta tags
    const userDataElement = document.getElementById('user-data');
    if (userDataElement) {
      try {
        const userData = JSON.parse(userDataElement.textContent || '{}');
        if (userData.user) {
          setUser(userData.user);
        }
        if (userData.membership) {
          setMembership(userData.membership);
        }
      } catch (e) {
        console.error('Failed to parse user data:', e);
      }
    }
  }

  return {
    // State
    user,
    membership,
    isAuthenticated,
    isLoading,
    // Getters
    userRole,
    canClaimResults,
    canResolveConflicts,
    canViewOrgDashboard,
    canInviteUsers,
    // Actions
    setUser,
    setMembership,
    logout,
    checkAuth,
  };
});
