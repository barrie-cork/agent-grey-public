<template>
  <div class="w-full px-6 py-4">
    <!-- Loading State -->
    <LoadingState
      v-if="loading"
      variant="spinner"
      class="py-12"
    />

    <!-- Error State -->
    <div v-else-if="error" class="py-4">
      <ErrorAlert
        variant="error"
        title="Error"
        :message="error"
      />
      <Button @click="loadConflict" class="mt-4">
        Try Again
      </Button>
    </div>

    <!-- Main Content -->
    <div v-else-if="conflict">
      <!-- Back to Review Overview -->
      <div class="flex items-center justify-between mb-4">
        <a
          v-if="sessionId"
          :href="`/review-results/overview/${sessionId}/`"
          class="inline-flex items-center gap-1.5 text-sm font-medium text-muted-foreground hover:text-foreground transition-colors"
        >
          <ArrowLeft class="h-4 w-4" />
          Back to Review Overview
        </a>

        <!-- SSE Connection Status (only show after initial connection was established) -->
        <div
          v-if="sseHasConnectedOnce && sseConnectionState !== 'connected' && sseConnectionState !== 'disconnected'"
          class="flex items-center gap-1.5 px-2 py-1 bg-warning/10 border border-warning/20 rounded text-[10px] font-bold uppercase tracking-widest text-warning-dark"
        >
          <Loader2 v-if="sseConnectionState === 'connecting' || sseConnectionState === 'reconnecting'" class="h-3 w-3 animate-spin" />
          {{ sseConnectionState === 'connecting' ? 'Connecting...' : sseConnectionState === 'reconnecting' ? 'Reconnecting...' : 'Connection error' }}
        </div>
      </div>

    <!-- Batch Position -->
    <div
      v-if="conflictsStore.sessionCounts.total > 0"
      class="flex items-center justify-between mb-4 px-1"
    >
      <p class="text-sm text-muted-foreground">
        Discussion {{ conflictsStore.sessionCounts.total - conflictsStore.sessionCounts.pending + 1 }} of {{ conflictsStore.sessionCounts.total }}
      </p>
      <p class="text-xs font-bold text-foreground">
        {{ conflictsStore.sessionProgressPercent }}% resolved
      </p>
    </div>

    <div class="grid grid-cols-1 lg:grid-cols-3 gap-8">
      <!-- Conflict Details (Left Column) -->
      <div class="lg:col-span-2 space-y-6">
        <!-- Conflict Header & Result -->
        <Card :class="[
          'border-scholar shadow-scholar overflow-hidden border-t-4',
          conflict.sla_info?.is_overdue || conflict.sla_info?.is_critical
            ? 'border-t-destructive ring-2 ring-destructive/30'
            : conflict.sla_info?.is_approaching
              ? 'border-t-warning ring-2 ring-warning/30'
              : 'border-t-warning'
        ]">
          <CardHeader class="bg-cool-grey-light/30 border-b border-scholar py-6">
            <div class="flex flex-row items-start justify-between">
              <div class="space-y-2">
                <div class="flex items-center gap-2">
                  <Badge variant="outline" class="border-warning text-warning-dark uppercase text-[10px] font-bold tracking-widest px-2">
                    {{ formatConflictType(conflict.conflict_type) }}
                  </Badge>
                  <StatusBadge :status="conflict.status" size="sm" />
                </div>
                <h1 class="text-3xl font-bold text-foreground leading-tight tracking-tight mt-1">
                  {{ conflict.result.title }}
                </h1>
                <div class="flex items-center gap-4 text-xs text-muted-foreground uppercase tracking-wider font-semibold">
                  <div class="flex items-center gap-1.5">
                    <AlertTriangle class="h-3.5 w-3.5 text-warning" />
                    {{ formatConflictType(conflict.conflict_type) }}
                  </div>
                  <div class="flex items-center gap-1.5 border-l border-scholar pl-4">
                    <Clock class="h-3.5 w-3.5" />
                    Identified: {{ formatDate(conflict.detected_at) }}
                  </div>
                  <div
                    v-if="conflict.sla_info && !conflict.sla_info.is_overdue"
                    class="flex items-center gap-1.5 border-l border-scholar pl-4"
                    :class="conflict.sla_info.is_critical ? 'text-destructive' : conflict.sla_info.is_approaching ? 'text-[color:var(--color-warning)]' : ''"
                  >
                    <Clock class="h-3.5 w-3.5" />
                    {{ Math.round(conflict.sla_info.hours_remaining) }}h remaining
                  </div>
                  <div
                    v-else-if="conflict.sla_info?.is_overdue"
                    class="flex items-center gap-1.5 border-l border-scholar pl-4 text-destructive"
                  >
                    <Clock class="h-3.5 w-3.5" />
                    Overdue by {{ Math.round(conflict.sla_info.hours_overdue) }}h
                  </div>
                </div>
              </div>
            </div>
          </CardHeader>
          <CardContent class="pt-6">
            <div class="relative px-6 py-4 bg-muted/30 border border-scholar border-dashed rounded-md">
              <h6 class="text-[10px] font-bold uppercase tracking-widest text-muted-foreground mb-2">Source Material</h6>
              <p class="font-serif leading-relaxed text-base text-foreground/80">
                {{ conflict.result.snippet || 'No snippet available for this record.' }}
              </p>
              <div v-if="conflict.result.source_organization || conflict.result.document_type" class="mt-3 flex flex-wrap gap-2">
                <span v-if="conflict.result.document_type" class="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-widest bg-muted text-muted-foreground">
                  {{ conflict.result.document_type }}
                </span>
                <span v-if="conflict.result.source_organization" class="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-widest bg-muted text-muted-foreground">
                  {{ conflict.result.source_organization }}
                </span>
              </div>
              <div class="mt-4 pt-4 border-t border-scholar/50">
                <Button
                  as="a"
                  :href="conflict.result.url"
                  target="_blank"
                  rel="noopener noreferrer"
                  variant="outline"
                  class="w-full gap-2"
                >
                  <ExternalLink class="h-4 w-4" />
                  Open Source in New Tab
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>

        <!-- Reviewer Decisions (The Core Conflict) -->
        <Card class="border-scholar shadow-scholar">
          <CardHeader class="border-b border-scholar py-4 bg-off-white">
            <div class="flex items-center justify-between">
              <h5 class="text-xs font-bold uppercase tracking-widest text-muted-foreground">Assessment Comparison</h5>
              <div v-if="shouldShowDecisions" class="flex items-center gap-1.5 px-2 py-0.5 bg-success/10 text-success-dark rounded border border-success/20 text-[10px] font-bold uppercase">
                <Eye class="h-3 w-3" /> Blind Deactivated
              </div>
              <div v-else class="flex items-center gap-1.5 px-2 py-0.5 bg-deep-navy/10 text-deep-navy rounded border border-deep-navy/20 text-[10px] font-bold uppercase">
                <ShieldCheck class="h-3 w-3" /> Active Blinding
              </div>
            </div>
          </CardHeader>
          <CardContent class="py-8">
            <!-- Blinded State -->
            <div v-if="!shouldShowDecisions && conflict.status === 'PENDING'" class="text-center space-y-4">
              <div class="inline-flex items-center justify-center w-20 h-20 rounded-full bg-deep-navy/5 border border-deep-navy/10">
                <EyeOff class="h-10 w-10 text-deep-navy/40" />
              </div>
              <div class="space-y-2">
                <h4 class="text-lg font-bold text-foreground">Independent Assessment in Progress</h4>
                <p class="text-sm text-muted-foreground max-w-md mx-auto leading-relaxed">
                  Assessments remain blinded to preserve reviewer independence and mitigate consensus bias, as per standard systematic review protocols.
                </p>
              </div>
              <div v-if="blindingStatus" class="inline-block px-4 py-2 bg-cool-grey-light/20 rounded border border-scholar">
                <p class="text-[10px] font-bold text-muted-foreground uppercase tracking-widest whitespace-nowrap">
                  Current Status: {{ blindingStatus.reason || 'Awaiting full reviewer cohort completion' }}
                </p>
              </div>
            </div>

            <!-- Revealed Decisions -->
            <div v-else class="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div
                v-for="(decision, index) in conflict.conflicting_decisions"
                :key="decision.id"
                class="relative p-5 border border-scholar rounded-lg bg-off-white hover:shadow-md transition-all group"
              >
                <div class="absolute -top-3 left-4 px-2 bg-white border border-scholar text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
                  Reviewer {{ index + 1 }}
                </div>

                <div class="space-y-4">
                  <div class="flex items-center justify-between mt-2">
                    <StatusBadge :status="decision.decision" size="md" />
                  </div>

                  <div v-if="decision.exclusion_reason" class="p-2.5 bg-destructive/5 border border-destructive/10 rounded">
                    <p class="text-[10px] font-bold text-destructive uppercase tracking-tight mb-1">Exclusion Rationale</p>
                    <p class="text-xs font-semibold text-foreground/90">{{ decision.exclusion_reason }}</p>
                  </div>

                  <div v-if="decision.notes" class="space-y-1">
                    <p class="text-[10px] font-bold text-muted-foreground uppercase tracking-tight">Reviewer Notes</p>
                    <p class="text-xs text-foreground/80 font-serif leading-relaxed italic border-l border-scholar pl-3 py-0.5">
                      "{{ decision.notes }}"
                    </p>
                  </div>

                  <div class="pt-3 border-t border-scholar border-dashed flex items-center justify-between text-[9px] text-muted-foreground uppercase tracking-widest font-bold">
                    <span>{{ decision.reviewer?.username || 'Redacted' }}</span>
                    <span>{{ formatDate(decision.decided_at) }}</span>
                  </div>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>

        <!-- Re-Vote Panel -->
        <RevotePanel
          v-if="activeRevoteProposal && conflict.status === 'PENDING'"
          :proposal="activeRevoteProposal"
          :conflict-id="props.id"
          :current-user-id="currentUserId"
          :has-already-voted="hasVotedOnActiveProposal"
          @accept-proposal="handleAcceptProposal"
          @submit-decision="handleSubmitRevoteDecision"
        />

        <!-- Audit Trail (Threaded Discussion) -->
        <Card class="border-scholar shadow-scholar overflow-hidden">
          <CardHeader class="bg-cool-grey-light/10 border-b border-scholar">
            <div class="flex items-center gap-2">
              <MessageSquareQuote class="h-4 w-4 text-deep-navy" />
              <h5 class="text-xs font-bold uppercase tracking-widest text-deep-navy">Discussion Thread</h5>
            </div>
          </CardHeader>
          <CardContent class="p-6">
            <CommentThread
              :comments="allComments"
              :can-comment="canComment"
              :can-propose-revote="canProposeRevote"
              :has-active-revote-proposal="!!activeRevoteProposal"
              :is-submitting="isSubmitting"
              :current-user-id="currentUserId"
              :show-criterion-tag="true"
              @post-comment="handlePostComment"
              @propose-revote="handleProposeRevote"
              @propose-straw-poll="handleProposeStrawPoll"
              @vote-respond="handleVoteRespond"
            />
          </CardContent>
        </Card>
      </div>

      <!-- Resolution Repository (Right Column) -->
      <div class="lg:col-span-1">
        <div class="sticky top-4 space-y-4">
          <Card class="border-scholar shadow-scholar border-t-4" :class="conflict.status === 'RESOLVED' ? 'border-t-success' : 'border-t-deep-navy'">
            <CardHeader class="pb-3 border-b border-scholar mb-4">
              <h5 class="text-[10px] uppercase tracking-widest text-muted-foreground font-bold">Joint Resolution</h5>
            </CardHeader>
            <CardContent class="space-y-6 pt-0">
              <!-- Resolution Output (Resolved) -->
              <div v-if="conflict.status === 'RESOLVED'" class="space-y-6">
                <div class="p-4 bg-success/5 border border-success/20 rounded-lg text-center">
                  <CheckCircle class="h-8 w-8 text-success mx-auto mb-2" />
                  <h4 class="text-lg font-bold text-foreground">Agreement Reached</h4>
                </div>

                <div class="space-y-4 divide-y divide-scholar">
                  <div class="pt-0 space-y-1">
                    <p class="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Final Decision</p>
                    <StatusBadge :status="conflict.final_decision" size="md" />
                  </div>
                  <div class="pt-4 space-y-1">
                    <p class="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Protocol Method</p>
                    <p class="text-sm font-bold text-deep-navy">{{ formatResolutionMethod(conflict.resolution_method) }}</p>
                  </div>
                  <div class="pt-4 space-y-1">
                    <p class="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Responsible Researcher</p>
                    <div class="flex items-center justify-between">
                      <span class="text-sm font-medium">{{ conflict.resolved_by?.username }}</span>
                      <span class="text-[10px] text-muted-foreground">{{ formatDate(conflict.resolved_at) }}</span>
                    </div>
                  </div>
                  <div v-if="conflict.resolution_notes" class="pt-4 space-y-1">
                    <p class="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Final Rationale</p>
                    <p class="text-xs italic leading-relaxed text-foreground/80 font-serif border-l-2 border-success/30 pl-3 py-1">
                      {{ conflict.resolution_notes }}
                    </p>
                  </div>
                </div>
              </div>

              <!-- Formal Resolution Process (Pending) -->
              <div v-else-if="shouldShowDecisions" class="space-y-6">
                <!-- Escalated banner -->
                <div
                  v-if="conflict.status === 'ESCALATED'"
                  class="flex items-start gap-2 p-3 bg-amber-50 border border-amber-200 rounded-md"
                >
                  <AlertTriangle class="h-4 w-4 text-amber-600 mt-0.5 shrink-0" />
                  <p class="text-xs text-amber-800 leading-relaxed">
                    This discussion has been referred for independent review. Awaiting resolution by a senior researcher.
                  </p>
                </div>

                <!-- Resolve form: only users with CONFLICT_RESOLVE (F1/PMD #282) -->
                <template v-if="canResolve">
                <p class="text-xs text-muted-foreground leading-relaxed italic">
                  Based on your discussion, what does the evidence show? Record the joint conclusion below.
                </p>

                <!-- Final Decision -->
                <div class="space-y-2">
                  <Label class="text-[10px] uppercase tracking-widest font-bold text-muted-foreground">Final Decision</Label>
                  <div class="grid grid-cols-1 gap-2">
                    <label
                      @click="selectFinalDecision('INCLUDE')"
                      :class="[
                        'flex items-center gap-3 px-4 py-3 border rounded-md cursor-pointer transition-all',
                        finalDecision === 'INCLUDE'
                          ? 'bg-success/10 border-success ring-1 ring-success/30'
                          : 'border-scholar hover:bg-muted/30'
                      ]"
                    >
                      <span
                        :class="[
                          'flex-shrink-0 w-4 h-4 rounded-full border-2 flex items-center justify-center',
                          finalDecision === 'INCLUDE' ? 'border-success bg-success' : 'border-muted-foreground/40'
                        ]"
                      >
                        <span v-if="finalDecision === 'INCLUDE'" class="w-1.5 h-1.5 rounded-full bg-white" />
                      </span>
                      <span class="text-sm font-medium text-foreground">Include</span>
                    </label>
                    <label
                      @click="selectFinalDecision('EXCLUDE')"
                      :class="[
                        'flex items-center gap-3 px-4 py-3 border rounded-md cursor-pointer transition-all',
                        finalDecision === 'EXCLUDE'
                          ? 'bg-destructive/10 border-destructive ring-1 ring-destructive/30'
                          : 'border-scholar hover:bg-muted/30'
                      ]"
                    >
                      <span
                        :class="[
                          'flex-shrink-0 w-4 h-4 rounded-full border-2 flex items-center justify-center',
                          finalDecision === 'EXCLUDE' ? 'border-destructive bg-destructive' : 'border-muted-foreground/40'
                        ]"
                      >
                        <span v-if="finalDecision === 'EXCLUDE'" class="w-1.5 h-1.5 rounded-full bg-white" />
                      </span>
                      <span class="text-sm font-medium text-foreground">Exclude</span>
                    </label>
                  </div>
                </div>

                <!-- Exclusion Reason (required when EXCLUDE selected) -->
                <div v-if="finalDecision === 'EXCLUDE'" class="space-y-2">
                  <Label class="text-[10px] uppercase tracking-widest font-bold text-muted-foreground">Exclusion Reason <span class="text-destructive">*</span></Label>
                  <input
                    v-model="exclusionReason"
                    type="text"
                    maxlength="100"
                    placeholder="Brief reason for exclusion..."
                    class="flex h-9 w-full rounded-md border border-scholar bg-transparent px-3 py-1 text-xs shadow-sm transition-colors placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-deep-navy disabled:cursor-not-allowed disabled:opacity-50"
                  />
                  <p class="text-[10px] text-muted-foreground">{{ exclusionReason.length }}/100 characters</p>
                </div>

                <!-- Rationale -->
                <div class="space-y-2">
                  <Label class="text-[10px] uppercase tracking-widest font-bold text-muted-foreground">Resolution Rationale</Label>
                  <Textarea
                    v-model="resolutionNotes"
                    placeholder="Document what the evidence showed and how agreement was reached..."
                    class="text-xs border-scholar focus:border-deep-navy min-h-[100px]"
                  />
                </div>

                <!-- Submit -->
                <Button
                  @click="handleResolveConflict"
                  :disabled="!canSubmitResolution || submittingResolution"
                  class="w-full bg-deep-navy hover:bg-deep-navy-dark text-white font-semibold h-10"
                >
                  <Loader2 v-if="submittingResolution" class="h-4 w-4 mr-2 animate-spin" />
                  <CheckSquare v-else class="h-4 w-4 mr-2" />
                  Submit Resolution
                </Button>
                </template>

                <!-- Escalate: only conflicting reviewers, pre-resolution (F1/PMD #282) -->
                <div v-if="canEscalate" class="pt-4 border-t border-scholar border-dashed">
                  <button
                    @click="handleEscalate"
                    :disabled="escalating"
                    class="w-full flex items-center justify-center gap-1.5 text-[10px] font-bold uppercase tracking-widest text-amber-700 hover:text-amber-800 py-2 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                  >
                    <Loader2 v-if="escalating" class="h-3.5 w-3.5 animate-spin" />
                    <ArrowUpCircle v-else class="h-3.5 w-3.5" />
                    Request Independent Review
                  </button>
                </div>

                <!-- View-only fallback: can neither resolve nor escalate -->
                <p
                  v-if="!canResolve && !canEscalate"
                  class="text-xs font-serif italic text-muted-foreground leading-relaxed text-center py-4"
                >
                  You can view this conflict; resolution is handled by a senior researcher.
                </p>
              </div>

              <!-- Blind Protection -->
              <div v-else class="text-center py-10 space-y-4">
                <ShieldAlert class="h-12 w-12 text-muted-foreground/30 mx-auto" />
                <p class="text-xs font-serif italic text-muted-foreground leading-relaxed px-4">
                  Resolution is available once all reviewers have completed their independent assessments.
                </p>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
    <!-- Rationale Dialog (shared for revote, straw poll, escalation) -->
    <RationaleDialog
      :open="activeDialog !== null"
      :title="dialogConfig.title"
      :description="dialogConfig.description"
      :placeholder="dialogConfig.placeholder"
      :required="dialogConfig.required"
      :submit-label="dialogConfig.submitLabel"
      @confirm="handleDialogConfirm"
      @cancel="handleDialogCancel"
    />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useConflictsStore } from '../stores/conflicts'
import { useConsensusDiscussionStore } from '../stores/consensusDiscussion'
import { useAuthStore } from '../stores/auth'
import { useConflictSSE } from '../composables/useConflictSSE'
import { getBlindingStatus } from '../api/sessions'
import type {
  DecisionType,
  BlindingStatus,
  ResolveConflictInput,
} from '../types'
import { BLINDING_CONSTANTS } from '../types'

// Lucide icons
import {
  AlertTriangle,
  ExternalLink,
  Eye,
  EyeOff,
  Clock,
  MessageSquareQuote,
  CheckCircle,
  CheckSquare,
  ArrowUpCircle,
  ShieldCheck,
  ShieldAlert,
  Loader2,
  ArrowLeft,
} from 'lucide-vue-next'

// Shadcn-vue components
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardHeader, CardContent } from '@/components/ui/card'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'

// Agent Grey components
import { StatusBadge } from '@/components/ui/status-badge'
import { LoadingState } from '@/components/ui/loading-state'
import { ErrorAlert, CommentThread, RevotePanel, RationaleDialog } from '@/components/shared'
import { toast } from 'vue-sonner'
import { extractErrorMessage } from '../lib/errors'

// Props
const props = defineProps<{
  id: string;
}>();

// Router
const router = useRouter();
const route = useRoute();

// Stores
const conflictsStore = useConflictsStore();
const discussionStore = useConsensusDiscussionStore();
const authStore = useAuthStore();

// Consensus discussion store state (primary data source)
const conflict = computed(() => discussionStore.conflictDetail);
const loading = computed(() => discussionStore.isLoading);
const error = computed({
  get: () => discussionStore.error,
  set: (value) => {
    if (value === null) discussionStore.clearError();
  }
});
const isSubmitting = computed(() => discussionStore.isSubmitting);
const allComments = computed(() => discussionStore.allComments);
const activeRevoteProposal = computed(() => discussionStore.activeRevoteProposal);
const canComment = computed(() => discussionStore.canComment);
const canProposeRevote = computed(() => discussionStore.canProposeRevote);
const hasVotedOnActiveProposal = computed(() => discussionStore.hasVotedOnActiveProposal);
const currentUserId = computed(() => authStore.user?.id || '');

// Blinding state
const blindingStatus = ref<BlindingStatus | null>(null);
const blindingError = ref<string | null>(null);

// Resolution state
const finalDecision = ref<DecisionType | ''>('');
const exclusionReason = ref('');
const resolutionNotes = ref('');
const submittingResolution = ref(false);
const escalating = ref(false);

// Rationale dialog state
type DialogContext = 'revote' | 'straw-poll' | 'escalate' | null;
const activeDialog = ref<DialogContext>(null);

const dialogConfig = computed(() => {
  switch (activeDialog.value) {
    case 'revote':
      return {
        title: 'Suggest Fresh Assessment',
        description: 'Explain why a fresh look at the evidence would help.',
        placeholder: 'What new perspective or evidence should reviewers consider?',
        required: true,
        submitLabel: 'Suggest Fresh Assessment',
      };
    case 'straw-poll':
      return {
        title: 'Propose Straw Poll',
        description: 'What question would you like the straw poll to address?',
        placeholder: 'Enter the question for the straw poll...',
        required: true,
        submitLabel: 'Create Poll',
      };
    case 'escalate':
      return {
        title: 'Request Independent Review',
        description: 'Provide an optional reason for requesting independent review.',
        placeholder: 'Why would an independent perspective help here? (optional)',
        required: false,
        submitLabel: 'Request Review',
      };
    default:
      return { title: '', description: '', placeholder: '', required: false, submitLabel: 'Submit' };
  }
});

// SSE connection
const {
  connect: connectSSE,
  disconnect: disconnectSSE,
  connectionState: sseConnectionState,
  hasConnectedOnce: sseHasConnectedOnce,
} = useConflictSSE(props.id);

// Stable session ID: captured from route query on mount, backfilled from conflict data.
// This survives conflict object replacement after resolution.
const storedSessionId = ref<string | null>(null);

// Computed
const sessionId = computed(() => {
  if (storedSessionId.value) return storedSessionId.value;
  const session = conflict.value?.result?.session;
  if (!session) return null;
  return typeof session === 'string' ? session : session.id;
});

const canSubmitResolution = computed(() => {
  if (!finalDecision.value) return false;
  if (finalDecision.value === 'EXCLUDE' && !exclusionReason.value.trim()) return false;
  return true;
});

// F1/PMD #282: gate the resolve form and escalate button on server-sent
// permission flags. Resolve and escalate are mutually exclusive, so without
// these gates every user saw a control whose submit then 403'd.
const canResolve = computed(() => conflict.value?._permissions?.can_resolve ?? false);
const canEscalate = computed(() => conflict.value?._permissions?.can_escalate ?? false);

// Check if decisions should be shown based on server-side blinding rules
const shouldShowDecisions = computed(() => {
  // If conflict is resolved, always show decisions
  if (conflict.value?.status === 'RESOLVED') {
    return true;
  }

  // If not blinded, show decisions
  if (!blindingStatus.value?.is_blinded) {
    return true;
  }

  // If blinded, check if result is fully reviewed
  // This is determined by the conflict having all required decisions
  // (conflict only created after all reviewers complete)
  const minReviewers = blindingStatus.value?.min_reviewers ?? BLINDING_CONSTANTS.MIN_REVIEWERS_DEFAULT;
  return conflict.value?.status === 'PENDING' &&
         (conflict.value?.conflicting_decisions?.length ?? 0) >= minReviewers;
});

// Methods

/**
 * Loads blinding status from the server for the current session.
 * Falls back to blinded mode if fetch fails for security.
 */
async function loadBlindingStatus(): Promise<void> {
  if (!conflict.value?.result?.session) {
    return;
  }

  try {
    const session = conflict.value.result.session;
    const sid = typeof session === 'string' ? session : session.id;
    blindingStatus.value = await getBlindingStatus(sid);
    blindingError.value = null;
  } catch (err) {
    console.error('Error loading blinding status:', err);
    blindingError.value = 'Failed to load blinding configuration. Decisions remain blinded for safety.';
    // Fail-safe: default to blinded to protect reviewer independence
    blindingStatus.value = {
      is_blinded: true,
      min_reviewers: BLINDING_CONSTANTS.MIN_REVIEWERS_DEFAULT,
      reason: 'Blinding status unavailable (server error) - defaulting to blinded'
    };
  }
}

async function loadConflict() {
  await discussionStore.fetchConflictDetail(props.id);

  if (conflict.value) {
    // Load blinding status from server
    await loadBlindingStatus();
  }
}

function selectFinalDecision(decision: DecisionType) {
  finalDecision.value = decision;
}

async function handlePostComment(content: string, parentId?: string, criterionTag?: string) {
  await discussionStore.addComment(props.id, {
    content,
    parent_comment: parentId,
    criterion_tag: criterionTag,
  });
}

function handleProposeRevote() {
  activeDialog.value = 'revote';
}

function handleProposeStrawPoll() {
  activeDialog.value = 'straw-poll';
}

async function handleDialogConfirm(text: string) {
  const context = activeDialog.value;
  activeDialog.value = null;

  if (context === 'revote') {
    if (!text) return;
    try {
      await discussionStore.createRevoteProposal(props.id, { rationale: text });
    } catch (err: any) {
      console.error('Error proposing re-vote:', err);
      toast.error(extractErrorMessage(err, 'Failed to suggest fresh assessment'));
    }
  } else if (context === 'straw-poll') {
    if (!text) return;
    try {
      await discussionStore.createDiscussionVote(props.id, text);
    } catch (err: any) {
      console.error('Error creating straw poll:', err);
      toast.error(extractErrorMessage(err, 'Failed to create straw poll'));
    }
  } else if (context === 'escalate') {
    escalating.value = true;
    try {
      await conflictsStore.escalateConflict(props.id, text || undefined);
      await discussionStore.fetchConflictDetail(props.id);
    } catch (err: any) {
      console.error('Error escalating conflict:', err);
      toast.error(extractErrorMessage(err, 'Failed to request independent review'));
    } finally {
      escalating.value = false;
    }
  }
}

function handleDialogCancel() {
  activeDialog.value = null;
}

async function handleVoteRespond(voteId: string, decision: string) {
  await discussionStore.submitDiscussionVoteResponse(props.id, voteId, decision);
}

async function handleAcceptProposal(proposalId: string) {
  await discussionStore.acceptProposal(props.id, proposalId);
}

async function handleSubmitRevoteDecision(
  decision: DecisionType,
  notes: string | undefined,
  confidenceLevel: number,
) {
  if (!activeRevoteProposal.value) return;

  await discussionStore.submitVote(props.id, activeRevoteProposal.value.id, {
    decision,
    notes,
    confidence_level: confidenceLevel,
  });
}

async function handleResolveConflict() {
  if (!canSubmitResolution.value) return;

  submittingResolution.value = true;

  try {
    const payload: ResolveConflictInput = {
      decision: finalDecision.value as DecisionType,
      resolution_notes: resolutionNotes.value || undefined,
    };
    if (finalDecision.value === 'EXCLUDE' && exclusionReason.value.trim()) {
      payload.exclusion_reason = exclusionReason.value.trim();
    }

    const resolved = await conflictsStore.submitResolution(props.id, payload);

    if (resolved) {
      // Refresh discussion store to show resolved state
      await discussionStore.fetchConflictDetail(props.id);

      // Fetch all pending conflicts from server to find the next one accurately
      if (sessionId.value) {
        await conflictsStore.fetchAllConflicts({ session_id: sessionId.value, status: 'PENDING' });
      }
      const nextConflict = conflictsStore.getNextPendingConflict(props.id);
      const query = sessionId.value ? { session_id: sessionId.value } : {};

      if (nextConflict) {
        toast.success('Discussion resolved - advancing to next');
        setTimeout(() => {
          router.push({ name: 'conflict-resolution', params: { id: nextConflict.id }, query });
        }, 1000);
      } else {
        toast.success('Discussion resolved successfully');
        setTimeout(() => {
          router.push({ name: 'conflicts', query });
        }, 1500);
      }
    }
  } catch (err: any) {
    console.error('Error resolving conflict:', err);
    toast.error(extractErrorMessage(err, 'Failed to resolve discussion'));
  } finally {
    submittingResolution.value = false;
  }
}

function handleEscalate() {
  activeDialog.value = 'escalate';
}

function formatConflictType(conflictType: string): string {
  const typeLabels: Record<string, string> = {
    INCLUDE_EXCLUDE: 'Include vs Exclude',
    EXCLUSION_REASON: 'Different Exclusion Reasons',
    LOW_CONFIDENCE: 'Low Confidence',
    INCLUDE_MAYBE: 'Include vs Maybe',
    EXCLUDE_MAYBE: 'Exclude vs Maybe',
    MULTIPLE_DISAGREEMENT: 'Multiple Disagreement',
  };
  return typeLabels[conflictType] || conflictType;
}

function formatResolutionMethod(method?: string): string {
  const methodLabels: Record<string, string> = {
    CONSENSUS: 'Consensus',
    ARBITRATION: 'Arbitration',
    LEAD_DECISION: 'Lead Decision',
    SENIOR_OVERRIDE: 'Senior Override',
  };
  return method ? methodLabels[method] || method : '';
}

function formatDate(dateString?: string): string {
  if (!dateString) return '';
  try {
    const date = new Date(dateString);
    return date.toLocaleDateString('en-GB', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return dateString;
  }
}

// SSE event handlers -- refetch conflict detail on real-time events
function handleSSEEvent() {
  discussionStore.fetchConflictDetail(props.id);
}

// Lifecycle
onMounted(async () => {
  // Capture session_id from query params before conflict load
  const rawSessionId = route.query.session_id;
  storedSessionId.value = typeof rawSessionId === 'string' ? rawSessionId : null;

  await loadConflict();

  // Backfill session ID from conflict data if not in query params
  if (!storedSessionId.value && conflict.value?.result?.session) {
    const session = conflict.value.result.session;
    storedSessionId.value = typeof session === 'string' ? session : session.id;
  }

  // Connect SSE for real-time updates
  try {
    connectSSE();
  } catch (err) {
    console.warn('SSE connection failed:', err);
  }

  // Listen for SSE-dispatched events to refetch data
  window.addEventListener('conflict:new_comment', handleSSEEvent);
  window.addEventListener('conflict:revote_proposed', handleSSEEvent);
  window.addEventListener('conflict:revote_accepted', handleSSEEvent);
  window.addEventListener('conflict:consensus_reached', handleSSEEvent);
  window.addEventListener('conflict:discussion_vote_updated', handleSSEEvent);
});

onUnmounted(() => {
  disconnectSSE();
  discussionStore.clearConflict();

  // Clean up SSE event listeners
  window.removeEventListener('conflict:new_comment', handleSSEEvent);
  window.removeEventListener('conflict:revote_proposed', handleSSEEvent);
  window.removeEventListener('conflict:revote_accepted', handleSSEEvent);
  window.removeEventListener('conflict:consensus_reached', handleSSEEvent);
  window.removeEventListener('conflict:discussion_vote_updated', handleSSEEvent);
});
</script>
