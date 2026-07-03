/**
 * Organisation Store
 * CRITICAL: Manages organisation context required by Django middleware
 */

import { defineStore } from 'pinia';
import { ref, computed } from 'vue';
import type { Organisation } from '../types';

export const useOrganisationStore = defineStore('organisation', () => {
  // State
  const currentOrganisation = ref<Organisation | null>(null);
  const organisations = ref<Organisation[]>([]);
  const isLoading = ref(false);

  // Getters
  const hasOrganisation = computed(() => currentOrganisation.value !== null);

  const organisationId = computed(() => currentOrganisation.value?.id || null);

  // Actions
  function setCurrentOrganisation(org: Organisation) {
    currentOrganisation.value = org;
    // Store in localStorage for persistence
    localStorage.setItem('currentOrganisation', JSON.stringify(org));
  }

  function setOrganisations(orgs: Organisation[]) {
    organisations.value = orgs;
  }

  function clearOrganisation() {
    currentOrganisation.value = null;
    localStorage.removeItem('currentOrganisation');
  }

  function loadOrganisationFromStorage() {
    const stored = localStorage.getItem('currentOrganisation');
    if (stored) {
      try {
        currentOrganisation.value = JSON.parse(stored);
      } catch (e) {
        console.error('Failed to load organisation from storage:', e);
        localStorage.removeItem('currentOrganisation');
      }
    }
  }

  function initializeFromUserData() {
    /**
     * Initialize organisation from Django-provided user_data JSON.
     * CRITICAL: Must be called before checkOrganisationContext()
     *
     * Pattern mirrored from frontend/src/stores/auth.ts checkAuth() method
     */
    const userDataElement = document.getElementById('user-data');
    if (userDataElement) {
      try {
        const userData = JSON.parse(userDataElement.textContent || '{}');

        // Load organisation from Django context
        if (userData.organisation) {
          currentOrganisation.value = userData.organisation;
          // Persist to localStorage
          localStorage.setItem('currentOrganisation', JSON.stringify(userData.organisation));
          console.log('✅ Organisation loaded from Django context:', userData.organisation.name);
        } else {
          console.warn('⚠️  No organisation in user_data - checking localStorage...');
          // Fallback to localStorage
          loadOrganisationFromStorage();
        }
      } catch (e) {
        console.error('Failed to parse user_data:', e);
        // Fallback to localStorage
        loadOrganisationFromStorage();
      }
    } else {
      console.warn('⚠️  No user-data element found - checking localStorage...');
      // Fallback to localStorage
      loadOrganisationFromStorage();
    }
  }

  function checkOrganisationContext() {
    // CRITICAL: Check if organisation context exists before making API calls
    if (!hasOrganisation.value) {
      console.warn('No organisation context - redirecting to selection');
      window.location.href = '/organisation/select/';
      return false;
    }
    return true;
  }

  return {
    // State
    currentOrganisation,
    organisations,
    isLoading,
    // Getters
    hasOrganisation,
    organisationId,
    // Actions
    setCurrentOrganisation,
    setOrganisations,
    clearOrganisation,
    loadOrganisationFromStorage,
    initializeFromUserData,
    checkOrganisationContext,
  };
});
