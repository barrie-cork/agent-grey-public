<template>
  <div class="w-full px-6 py-4" data-testid="screening-decision">
    <!-- Loading State -->
    <LoadingState
      v-if="loading"
      variant="spinner"
      message="Loading result..."
    />

    <!-- Error State -->
    <div v-else-if="error" class="w-full px-6 py-4">
      <ErrorAlert
        variant="error"
        title="Error"
        :message="error"
      >
        <Button @click="loadResult" class="mt-2">Try Again</Button>
      </ErrorAlert>
    </div>

    <!-- Main Content -->
    <div v-else-if="result" class="grid grid-cols-1 lg:grid-cols-3 gap-6">
      <!-- Result Display (Left Column) -->
      <div class="lg:col-span-2 space-y-4">
        <Card class="border-scholar shadow-scholar overflow-hidden border-t-4 border-t-deep-navy">
          <CardHeader class="bg-cool-grey-light/30 border-b border-scholar py-6">
            <div class="flex flex-row items-start justify-between gap-4">
              <div class="space-y-2">
                <div class="flex items-center gap-2">
                  <Badge variant="outline" class="border-deep-navy text-deep-navy uppercase text-[10px] font-bold tracking-widest px-2">
                    Active Protocol: {{ screeningStage }}
                  </Badge>
                  <div class="flex items-center gap-1 text-[9px] font-bold text-muted-foreground uppercase tracking-tight bg-white/50 px-2 py-0.5 rounded border border-scholar">
                    <ShieldCheck class="h-3 w-3 text-deep-navy" /> Verified Corpus
                  </div>
                </div>
                <h1 class="text-3xl font-bold text-foreground leading-tight tracking-tight mt-1">
                  {{ result.title }}
                </h1>
                <div class="flex flex-wrap items-center gap-4 text-xs text-muted-foreground uppercase tracking-wider font-semibold">
                  <div v-if="result.source_name" class="flex items-center gap-1.5">
                    <Database class="h-3.5 w-3.5" />
                    {{ result.source_name }}
                  </div>
                  <div v-if="result.date_published" class="flex items-center gap-1.5 border-l border-scholar pl-4">
                    <Calendar class="h-3.5 w-3.5" />
                    {{ formatDate(result.date_published) }}
                  </div>
                </div>
              </div>
              <Badge variant="secondary" class="bg-deep-navy text-off-white px-3 py-1">{{ screeningStage }}</Badge>
            </div>
          </CardHeader>
          
          <CardContent class="pt-8 space-y-8">
            <!-- Snippet Section -->
            <div v-if="result.snippet" class="space-y-3">
              <h6 class="text-xs font-bold uppercase tracking-widest text-muted-foreground flex items-center gap-1.5">
                <AlignLeft class="h-3.5 w-3.5" /> Research Abstract / Snippet
              </h6>
              <div class="relative px-6 py-4 bg-off-white border border-scholar rounded-md shadow-inner">
                <p class="font-serif leading-relaxed text-lg italic text-foreground/90">
                  "{{ result.snippet }}"
                </p>
              </div>
            </div>

            <!-- Metadata Grid -->
            <div class="grid grid-cols-1 md:grid-cols-2 gap-8 pt-6 border-t border-scholar">
              <div v-if="result.authors" class="space-y-1">
                <h6 class="text-xs font-bold uppercase tracking-widest text-muted-foreground">Contributing Authors</h6>
                <p class="text-sm font-medium">{{ result.authors }}</p>
              </div>
              <div v-if="result.is_duplicate">
                <Alert class="border-warning bg-warning/5 py-3">
                  <AlertTriangle class="h-4 w-4 text-warning" />
                  <AlertDescription class="text-xs">
                    <span class="font-bold text-warning-dark">METHODOLOGICAL ALERT:</span> Potential duplicate identified within current search corpus.
                  </AlertDescription>
                </Alert>
              </div>
            </div>

            <!-- Review Metadata Toolset -->
            <div class="pt-6 flex items-center justify-between border-t border-scholar border-dashed">
              <div class="inline-flex items-center gap-3 px-4 py-2 bg-muted/20 rounded-full border border-scholar">
                <Clock class="h-4 w-4 text-muted-foreground" />
                <span class="text-xs font-bold text-muted-foreground uppercase tracking-widest">Active Review Time:</span>
                <span class="text-sm font-mono font-bold text-deep-navy">{{ formattedTime }}</span>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      <!-- Decision Form (Right Column) -->
      <div class="lg:col-span-1">
        <div class="sticky top-4 space-y-4">
          <Card class="border-scholar shadow-scholar border-t-4 border-t-teal-blue rounded-md">
            <CardHeader class="pb-2 border-b border-scholar mb-3 pt-3 px-4">
              <CardTitle class="text-sm uppercase tracking-widest text-muted-foreground font-bold">Protocol Implementation</CardTitle>
            </CardHeader>
            <CardContent class="space-y-4 pt-0 px-4 pb-4">
              <!-- Source URL Access -->
              <div v-if="result.url" class="p-3 bg-muted/50 rounded border border-scholar">
                <p class="text-[10px] font-bold uppercase text-muted-foreground mb-1.5 flex items-center gap-1">
                  <ExternalLink class="h-3 w-3" /> External Repository Access
                </p>
                <a
                  :href="result.url"
                  target="_blank"
                  class="text-xs text-teal-blue hover:underline break-all block truncate font-medium"
                  :title="result.url"
                  @click="handleUrlClick"
                >
                  {{ result.url }}
                </a>
              </div>

              <!-- Decision Matrix (Compact VSA Component) -->
              <DecisionButtons
                :current-decision="selectedDecision.toLowerCase() as Decision"
                :disabled="submitting"
                @decision="handleDecision"
              />

              <!-- Exclusion Rationale - PRISMA Specific -->
              <div v-if="selectedDecision === 'EXCLUDE'" class="space-y-2 p-3 bg-destructive/5 rounded border border-destructive/20 animate-in fade-in slide-in-from-top-2">
                <Label class="text-destructive font-bold flex items-center gap-1.5 text-[10px] uppercase tracking-widest">
                  <AlertCircle class="h-3.5 w-3.5" /> Exclusion Rationale
                </Label>
                <Select v-model="exclusionReason">
                  <SelectTrigger class="border-destructive/30 focus:ring-destructive bg-background h-9">
                    <SelectValue placeholder="Protocol reason" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="wrong_population">Population Ineligible</SelectItem>
                    <SelectItem value="wrong_interest">Focus/Outcome Ineligible</SelectItem>
                    <SelectItem value="wrong_context">Context/Setting Ineligible</SelectItem>
                    <SelectItem value="duplicate">Verified Duplicate</SelectItem>
                    <SelectItem value="not_grey_lit">Published Literature (Exclude)</SelectItem>
                    <SelectItem value="no_access">Full Text Unretrievable</SelectItem>
                    <SelectItem value="low_quality">Insufficient Evidence Quality</SelectItem>
                    <SelectItem value="other">Other (documented below)</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <!-- Evaluative Metadata -->
              <div class="space-y-3 pt-3 border-t border-scholar border-dashed">
                <ConfidenceSelector
                  v-model="confidenceLevel"
                  :disabled="submitting"
                />

                <div class="space-y-2">
                  <Label class="text-[10px] uppercase tracking-widest font-bold text-muted-foreground">Researcher Narrative / Notes</Label>
                  <Textarea
                    v-model="notes"
                    placeholder="Document methodological reasoning here..."
                    class="text-xs border-scholar focus:border-deep-navy resize-none min-h-[100px] leading-relaxed"
                  />
                </div>
              </div>

              <!-- Execute Decision -->
              <Button
                size="lg"
                class="w-full font-bold shadow-md bg-deep-navy hover:bg-deep-navy-dark"
                :disabled="!canSubmit || submitting"
                @click="submitReview"
              >
                <Loader2 v-if="submitting" class="mr-2 h-4 w-4 animate-spin" />
                <Send v-else class="mr-2 h-4 w-4" />
                {{ submitting ? 'Submitting Record...' : 'Confirm & Record Decision' }}
              </Button>

            </CardContent>
          </Card>
        </div>
      </div>
    </div>

    <!-- Success Modal -->
    <Dialog :open="showSuccessModal" @update:open="showSuccessModal = $event">
      <DialogContent class="sm:max-w-md">
        <DialogHeader :class="dialogHeaderClass">
          <DialogTitle>{{ modalTitle }}</DialogTitle>
        </DialogHeader>
        <DialogDescription>
          <p class="mb-4">{{ modalMessage }}</p>
          <Alert
            v-if="decisionResponse?.conflict_type"
            class="border-[color:var(--color-warning)] bg-[color:var(--color-warning-light)]"
          >
            <AlertTriangle class="h-4 w-4 text-[color:var(--color-warning-dark)]" />
            <AlertDescription>
              <strong>Conflict Type:</strong> {{ formatConflictType(decisionResponse.conflict_type) }}
            </AlertDescription>
          </Alert>
        </DialogDescription>
        <DialogFooter class="gap-2 sm:gap-0">
          <Button
            v-if="decisionResponse?.conflict_id"
            variant="outline"
            class="border-[color:var(--color-warning)] text-[color:var(--color-warning-dark)] hover:bg-[color:var(--color-warning-light)]"
            @click="goToConflict"
          >
            View Conflict
          </Button>
          <Button @click="goToNextResult">
            {{ autoAdvanceText }}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import { getResult, submitDecision, trackUrlAccess } from '../api/results';
import { useTimer } from '../composables/useTimer';
import { useKeyboardShortcuts } from '../composables/useKeyboardShortcuts';
import type {
  ProcessedResult,
  DecisionType,
  DecisionResponse,
} from '../types';

// Shadcn-vue components
import { Card, CardHeader, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog';
import {
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
} from '@/components/ui/select';
import { Alert, AlertDescription } from '@/components/ui/alert';

// Phase 04 components
import { DecisionButtons, type Decision } from '@/components/ui/decision-buttons';
import ConfidenceSelector from '@/components/ui/confidence-selector/ConfidenceSelector.vue';
import { LoadingState } from '@/components/ui/loading-state';
import { ErrorAlert } from '@/components/shared';

// Lucide icons
import { ExternalLink, Send, Loader2, ShieldCheck, Database, Calendar, AlignLeft, Clock } from 'lucide-vue-next';

// Props
const props = defineProps<{
  id: string;
}>();

// Router
const router = useRouter();

// State
const result = ref<ProcessedResult | null>(null);
const loading = ref(true);
const error = ref<string | null>(null);
const submitting = ref(false);

// Form State
const selectedDecision = ref<DecisionType | ''>('');
const exclusionReason = ref('');
const confidenceLevel = ref(2); // Default to MEDIUM
const notes = ref('');
const validationErrors = ref<Record<string, string>>({});

// Timer (composable)
const { elapsedSeconds, formattedTime, startTimer, stopTimer } = useTimer();

// Success Modal State
const showSuccessModal = ref(false);
const decisionResponse = ref<DecisionResponse | null>(null);

// Screening stage (grey literature: always SCREENING)
const screeningStage = ref<'SCREENING'>('SCREENING');

// Computed Properties
const canSubmit = computed(() => {
  if (!selectedDecision.value) return false;
  if (selectedDecision.value === 'EXCLUDE' && !exclusionReason.value) return false;
  return true;
});

const modalTitle = computed(() => {
  if (!decisionResponse.value) return 'Decision Submitted';

  const statusTitles: Record<string, string> = {
    consensus_reached: 'Consensus Reached',
    awaiting_second_reviewer: 'Decision Recorded',
    conflict_detected: 'Conflict Detected',
  };

  return statusTitles[decisionResponse.value.status ?? ''] || 'Decision Submitted';
});

const dialogHeaderClass = computed(() => {
  if (!decisionResponse.value) return 'bg-[color:var(--color-success-light)] rounded-t-lg';

  const statusClasses: Record<string, string> = {
    consensus_reached: 'bg-[color:var(--color-success-light)] rounded-t-lg',
    awaiting_second_reviewer: 'bg-[color:var(--color-info-light)] rounded-t-lg',
    conflict_detected: 'bg-[color:var(--color-warning-light)] rounded-t-lg',
  };

  return statusClasses[decisionResponse.value.status ?? ''] || 'bg-[color:var(--color-success-light)] rounded-t-lg';
});

const modalMessage = computed(() => {
  return decisionResponse.value?.message || 'Your decision has been recorded successfully.';
});

const autoAdvanceText = computed(() => {
  return decisionResponse.value?.conflict_id ? 'Continue to Next Result' : 'Next Result';
});

// Methods
async function loadResult() {
  loading.value = true;
  error.value = null;

  try {
    result.value = await getResult(props.id);

    // Restore existing decision if user already decided on this result
    if (result.value?.my_decision) {
      selectedDecision.value = result.value.my_decision.toUpperCase() as DecisionType;
    }

    startTimer();
  } catch (err: any) {
    error.value = err.response?.data?.detail || 'Failed to load result. Please try again.';
    console.error('Error loading result:', err);
  } finally {
    loading.value = false;
  }
}

function selectDecision(decision: DecisionType) {
  selectedDecision.value = decision;

  // Clear exclusion reason if not EXCLUDE
  if (decision !== 'EXCLUDE') {
    exclusionReason.value = '';
    delete validationErrors.value.exclusionReason;
  }
}

// Handler for Phase 04 DecisionButtons (converts lowercase to uppercase)
function handleDecision(decision: Decision) {
  const uppercaseDecision = decision.toUpperCase() as DecisionType;
  selectDecision(uppercaseDecision);
}

function validateForm(): boolean {
  validationErrors.value = {};

  if (!selectedDecision.value) {
    validationErrors.value.decision = 'Please select a decision';
    return false;
  }

  if (selectedDecision.value === 'EXCLUDE' && !exclusionReason.value) {
    validationErrors.value.exclusionReason = 'Exclusion reason is required when excluding a result';
    return false;
  }

  return true;
}

async function submitReview() {
  if (!validateForm()) {
    return;
  }

  submitting.value = true;
  stopTimer();

  try {
    const timeSpentSeconds = elapsedSeconds.value;

    const decisionData = {
      decision: selectedDecision.value as DecisionType,
      exclusion_reason: selectedDecision.value === 'EXCLUDE' ? exclusionReason.value : undefined,
      confidence_level: confidenceLevel.value,  // Send integer 1-3, not string
      notes: notes.value || undefined,
      time_spent_seconds: timeSpentSeconds,
      screening_stage: screeningStage.value,
    };

    const response = await submitDecision(props.id, decisionData);
    decisionResponse.value = response;
    showSuccessModal.value = true;

  } catch (err: any) {
    error.value = err.response?.data?.detail || 'Failed to submit decision. Please try again.';
    console.error('Error submitting decision:', err);

    // Restart timer if submission failed
    startTimer();
  } finally {
    submitting.value = false;
  }
}

function goToNextResult() {
  // Navigate to work queue to claim next result
  router.push('/work-queue');
}

function goToConflict() {
  if (decisionResponse.value?.conflict_id) {
    router.push(`/conflicts/${decisionResponse.value.conflict_id}`);
  }
}

function handleUrlClick() {
  if (result.value?.session && result.value?.id) {
    const sessionId = typeof result.value.session === 'string'
      ? result.value.session
      : (result.value.session as any).id;
    trackUrlAccess(sessionId, result.value.id).catch((err) => {
      console.error('Error tracking URL access:', err);
    });
  }
}

function formatDate(dateString: string): string {
  try {
    const date = new Date(dateString);
    return date.toLocaleDateString('en-GB', {
      year: 'numeric',
      month: 'long',
      day: 'numeric',
    });
  } catch {
    return dateString;
  }
}

function formatConflictType(conflictType: string): string {
  const typeLabels: Record<string, string> = {
    INCLUDE_EXCLUDE: 'Include vs Exclude',
    INCLUDE_MAYBE: 'Include vs Maybe',
    EXCLUDE_MAYBE: 'Exclude vs Maybe',
    MULTIPLE_DISAGREEMENT: 'Multiple Disagreement',
  };
  return typeLabels[conflictType] || conflictType;
}

// Keyboard shortcuts (composable handles mount/unmount lifecycle)
useKeyboardShortcuts({
  i: () => selectDecision('INCLUDE'),
  m: () => selectDecision('MAYBE'),
  e: () => selectDecision('EXCLUDE'),
});

// Lifecycle
onMounted(() => {
  loadResult();
});
</script>

<style scoped>
/* Required field indicator */
.required::after {
  content: ' *';
  color: hsl(var(--destructive));
}
</style>
