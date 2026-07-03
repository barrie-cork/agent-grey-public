<template>
  <div class="min-h-screen flex flex-col">
    <!-- Navigation -->
    <nav class="bg-primary text-primary-foreground">
      <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div class="flex items-center justify-between h-16">
          <!-- Brand -->
          <router-link to="/" class="flex items-center gap-2 font-semibold text-primary-foreground hover:text-primary-foreground/80 transition-colors">
            <Search class="h-5 w-5" />
            Agent Grey - Dual Screening
          </router-link>

          <!-- Desktop Navigation -->
          <div class="hidden md:flex items-center gap-1">
            <router-link
              v-if="showWorkQueue"
              to="/work-queue"
              class="flex items-center gap-1.5 px-3 py-2 rounded-md text-sm font-medium text-primary-foreground/70 hover:bg-white/10 hover:text-primary-foreground transition-colors"
              active-class="bg-white/10 text-primary-foreground"
            >
              <ClipboardList class="h-4 w-4" />
              Work Queue
            </router-link>

            <router-link
              to="/conflicts"
              class="flex items-center gap-1.5 px-3 py-2 rounded-md text-sm font-medium text-primary-foreground/70 hover:bg-white/10 hover:text-primary-foreground transition-colors"
              active-class="bg-white/10 text-primary-foreground"
            >
              <AlertTriangle class="h-4 w-4" />
              Conflicts
              <Badge v-if="conflictsCount > 0" variant="destructive" class="ml-1">
                {{ conflictsCount }}
              </Badge>
            </router-link>

            <router-link
              v-if="canViewDashboard"
              to="/dashboard"
              class="flex items-center gap-1.5 px-3 py-2 rounded-md text-sm font-medium text-primary-foreground/70 hover:bg-white/10 hover:text-primary-foreground transition-colors"
              active-class="bg-white/10 text-primary-foreground"
            >
              <TrendingUp class="h-4 w-4" />
              Dashboard
            </router-link>

            <!-- User Dropdown -->
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" class="flex items-center gap-1.5 text-primary-foreground/70 hover:bg-white/10 hover:text-primary-foreground">
                  <UserCircle class="h-4 w-4" />
                  {{ userName }}
                  <ChevronDown class="h-4 w-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" class="w-48">
                <DropdownMenuLabel>{{ userRole }}</DropdownMenuLabel>
                <DropdownMenuSeparator />
                <DropdownMenuItem asChild>
                  <a href="/accounts/profile/" class="w-full">Profile</a>
                </DropdownMenuItem>
                <DropdownMenuItem @click="handleLogout">
                  Logout
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>

          <!-- Mobile Menu Button -->
          <Button
            variant="ghost"
            size="icon"
            class="md:hidden text-primary-foreground/70 hover:bg-white/10 hover:text-primary-foreground"
            @click="mobileMenuOpen = !mobileMenuOpen"
            :aria-expanded="mobileMenuOpen"
            aria-label="Toggle navigation"
          >
            <Menu v-if="!mobileMenuOpen" class="h-6 w-6" />
            <X v-else class="h-6 w-6" />
          </Button>
        </div>

        <!-- Mobile Navigation -->
        <div v-show="mobileMenuOpen" class="md:hidden pb-4 space-y-1">
          <router-link
            v-if="showWorkQueue"
            to="/work-queue"
            class="flex items-center gap-2 px-3 py-2 rounded-md text-base font-medium text-primary-foreground/70 hover:bg-white/10 hover:text-primary-foreground transition-colors"
            active-class="bg-white/10 text-primary-foreground"
            @click="mobileMenuOpen = false"
          >
            <ClipboardList class="h-5 w-5" />
            Work Queue
          </router-link>

          <router-link
            to="/conflicts"
            class="flex items-center gap-2 px-3 py-2 rounded-md text-base font-medium text-primary-foreground/70 hover:bg-white/10 hover:text-primary-foreground transition-colors"
            active-class="bg-white/10 text-primary-foreground"
            @click="mobileMenuOpen = false"
          >
            <AlertTriangle class="h-5 w-5" />
            Conflicts
            <Badge v-if="conflictsCount > 0" variant="destructive" class="ml-1">
              {{ conflictsCount }}
            </Badge>
          </router-link>

          <router-link
            v-if="canViewDashboard"
            to="/dashboard"
            class="flex items-center gap-2 px-3 py-2 rounded-md text-base font-medium text-primary-foreground/70 hover:bg-white/10 hover:text-primary-foreground transition-colors"
            active-class="bg-white/10 text-primary-foreground"
            @click="mobileMenuOpen = false"
          >
            <TrendingUp class="h-5 w-5" />
            Dashboard
          </router-link>

          <div class="border-t border-primary-foreground/20 pt-4 mt-4">
            <div class="px-3 py-2 text-sm text-primary-foreground/50">{{ userRole }}</div>
            <a
              href="/accounts/profile/"
              class="flex items-center gap-2 px-3 py-2 rounded-md text-base font-medium text-primary-foreground/70 hover:bg-white/10 hover:text-primary-foreground transition-colors"
            >
              <UserCircle class="h-5 w-5" />
              Profile
            </a>
            <button
              @click="handleLogout"
              class="flex items-center gap-2 w-full px-3 py-2 rounded-md text-base font-medium text-primary-foreground/70 hover:bg-white/10 hover:text-primary-foreground transition-colors"
            >
              Logout
            </button>
          </div>
        </div>
      </div>
    </nav>

    <!-- Main Content -->
    <main class="flex-1">
      <router-view v-slot="{ Component }">
        <transition name="fade" mode="out-in">
          <component :is="Component" />
        </transition>
      </router-view>
    </main>

    <!-- Footer -->
    <footer class="bg-muted py-3 mt-auto">
      <div class="max-w-7xl mx-auto px-4 text-center text-muted-foreground">
        <small>&copy; 2026 Agent Grey. All rights reserved.</small>
      </div>
    </footer>

    <!-- Global Loading Overlay -->
    <div v-if="isGlobalLoading" class="fixed inset-0 z-50 bg-black/50 flex items-center justify-center">
      <LoadingState variant="spinner" size="lg" />
    </div>

    <!-- Feedback Widget -->
    <FeedbackWidget />

    <!-- Global Toast Notifications -->
    <Toaster position="top-right" :duration="4000" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { useAuthStore } from './stores/auth';
import { useOrganisationStore } from './stores/organisation';
import { useWorkQueueStore } from './stores/workQueue';

// Shadcn-vue components
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
} from '@/components/ui/dropdown-menu';

// Phase 04 components
import { LoadingState } from '@/components/ui/loading-state';
import { Toaster } from '@/components/ui/sonner';
import { FeedbackWidget } from '@/components/shared';

// Lucide icons
import {
  Search,
  ClipboardList,
  AlertTriangle,
  TrendingUp,
  UserCircle,
  ChevronDown,
  Menu,
  X,
} from 'lucide-vue-next';

const authStore = useAuthStore();
const orgStore = useOrganisationStore();
const workQueueStore = useWorkQueueStore();

// Mobile menu state
const mobileMenuOpen = ref(false);

// Session context (injected by Django vue_spa view when session_id in query params)
const sessionContext = ref<{ id: string; is_workflow_2: boolean } | null>(null);

// Computed properties
const userName = computed(() => {
  const user = authStore.user;
  if (!user) return 'User';
  return user.first_name || user.username;
});

const userRole = computed(() => {
  const role = authStore.userRole;
  if (!role) return '';
  return role.replace(/_/g, ' ');
});

const canViewDashboard = computed(() => authStore.canViewOrgDashboard);

const conflictsCount = computed(() => workQueueStore.conflicts.length);

const showWorkQueue = computed(() => !sessionContext.value?.is_workflow_2);

const isGlobalLoading = computed(() => false); // Can be connected to a global loading state

// Methods
function handleLogout() {
  authStore.logout();
}

// Lifecycle
onMounted(() => {
  // Check authentication and organisation context
  authStore.checkAuth();
  orgStore.initializeFromUserData();  // Load from template first, localStorage fallback

  // Load session context if injected by Django
  const userDataElement = document.getElementById('user-data');
  if (userDataElement) {
    try {
      const userData = JSON.parse(userDataElement.textContent || '{}');
      if (userData.session) {
        sessionContext.value = userData.session;
      }
    } catch {
      // Ignore parse errors; auth store handles user data
    }
  }

  // Validate organisation context (will not redirect if loaded successfully)
  orgStore.checkOrganisationContext();
});
</script>

<style scoped>
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
