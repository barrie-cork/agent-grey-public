<template>
  <div class="w-full px-6 py-4">
    <!-- Header -->
    <div class="flex flex-col md:flex-row md:items-end md:justify-between mb-10 gap-4">
      <div class="space-y-1">
        <h1 class="text-3xl font-bold text-foreground">Methodological Dashboard</h1>
        <p class="text-sm text-muted-foreground uppercase tracking-widest font-semibold flex items-center gap-2">
          <ShieldCheck class="h-4 w-4 text-deep-navy" />
          Review Session: {{ sessionId || 'Active Protocol' }}
        </p>
      </div>
      <div class="flex items-center gap-3">
        <div v-if="isConnected" class="flex items-center gap-1.5 px-3 py-1.5 bg-success/5 border border-success/20 rounded-full">
          <span class="relative flex h-2 w-2">
            <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-success opacity-75"></span>
            <span class="relative inline-flex rounded-full h-2 w-2 bg-success"></span>
          </span>
          <span class="text-[10px] font-bold uppercase tracking-widest text-success-dark">Live Audit Stream</span>
        </div>
        <Button
          variant="outline"
          @click="handleRefresh"
          :disabled="isLoading"
          class="border-scholar hover:bg-off-white font-bold text-xs uppercase tracking-tight h-9"
        >
          <RefreshCw :class="{ 'animate-spin': isLoading }" class="h-3.5 w-3.5 mr-2" />
          Synchronise Data
        </Button>
      </div>
    </div>

    <!-- Error Alerts (Moved inside content area for density) -->
    <div class="space-y-4 mb-8">
      <ErrorAlert
        v-if="error"
        title="Dashboard Sync Failure"
        :message="error"
        dismissible
        @dismiss="error = null"
      />

      <Alert
        v-if="blindingError"
        class="border-warning bg-warning/5 border-l-4"
      >
        <AlertCircle class="h-4 w-4 text-warning-dark" />
        <AlertDescription class="text-xs font-semibold text-warning-dark">
          {{ blindingError }}
        </AlertDescription>
      </Alert>
    </div>

    <!-- Loading State -->
    <LoadingState
      v-if="isLoading && !stats"
      variant="spinner"
      size="lg"
      message="Calculating metrics..."
    />

    <!-- Dashboard Content -->
    <div v-else-if="stats" class="space-y-8">
      <!-- Primary Methodological Metrics -->
      <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        <!-- IRR (Cohen's Kappa) Card -->
        <Card class="border-scholar shadow-scholar border-t-4 border-t-deep-navy">
          <CardContent class="p-6">
            <div class="flex justify-between items-start mb-6">
              <div class="space-y-1">
                <h6 class="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Inter-Rater Reliability</h6>
                <p class="text-xs font-serif italic text-muted-foreground">Cohen's Kappa (&kappa;) Coefficient</p>
              </div>
              <div class="p-2 bg-deep-navy/5 rounded">
                <TrendingUp class="h-5 w-5 text-deep-navy" />
              </div>
            </div>
            
            <div class="flex items-baseline gap-2 mb-4">
              <h2 class="text-5xl font-bold tracking-tighter" :class="kappaColorClass">
                {{ formatKappa(cohensKappa) }}
              </h2>
              <Badge :variant="kappaBadgeVariant" class="uppercase text-[9px] font-bold px-1.5 py-0 transform -translate-y-2">
                {{ kappaInterpretation }}
              </Badge>
            </div>

            <div class="space-y-3 pt-4 border-t border-scholar">
              <div class="flex justify-between items-center text-xs">
                <span class="text-muted-foreground">Observed Agreement</span>
                <span class="font-bold font-mono">{{ percentageAgreement?.toFixed(1) ?? 0 }}%</span>
              </div>
              <div v-if="cohensKappa != null && cohensKappa < 0.70" class="p-2 bg-warning/5 border border-warning/20 rounded flex items-center gap-2">
                <AlertTriangle class="h-3.5 w-3.5 text-warning" />
                <span class="text-[10px] font-bold text-warning-dark uppercase tracking-tight">Below Cochrane Threshold (0.70)</span>
              </div>
            </div>
          </CardContent>
        </Card>

        <!-- Progress Card -->
        <Card class="border-scholar shadow-scholar border-t-4 border-t-success">
          <CardContent class="p-6">
            <div class="flex justify-between items-start mb-6">
              <div class="space-y-1">
                <h6 class="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Screening Saturation</h6>
                <p class="text-xs font-serif italic text-muted-foreground">Protocol Execution Progress</p>
              </div>
              <div class="p-2 bg-success/5 rounded">
                <ClipboardCheck class="h-5 w-5 text-success-dark" />
              </div>
            </div>
            
            <div class="flex items-baseline gap-2 mb-4">
              <h2 class="text-5xl font-bold tracking-tighter text-foreground">
                {{ progressPercentage }}%
              </h2>
              <span class="text-xs font-bold text-muted-foreground uppercase tracking-widest">Complete</span>
            </div>

            <div class="space-y-4 pt-4 border-t border-scholar">
              <div class="flex justify-between items-center text-xs">
                <span class="text-muted-foreground">Records Screened</span>
                <span class="font-bold font-mono">{{ stats.overview.reviewed }} / {{ stats.overview.total_results }}</span>
              </div>
              <Progress :model-value="progressPercentage" class="h-1.5 bg-cool-grey-light" />
            </div>
          </CardContent>
        </Card>

        <!-- Conflicts Card -->
        <Card class="border-scholar shadow-scholar border-t-4 border-t-warning">
          <CardContent class="p-6">
            <div class="flex justify-between items-start mb-6">
              <div class="space-y-1">
                <h6 class="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Methodological Variance</h6>
                <p class="text-xs font-serif italic text-muted-foreground">Pending Conflict Resolutions</p>
              </div>
              <div class="p-2 bg-warning/5 rounded">
                <AlertTriangle class="h-5 w-5 text-warning" />
              </div>
            </div>
            
            <div class="flex items-baseline gap-2 mb-4">
              <h2 class="text-5xl font-bold tracking-tighter text-warning-dark">
                {{ stats.overview.pending_conflicts }}
              </h2>
              <span class="text-xs font-bold text-muted-foreground uppercase tracking-widest">Conflicts</span>
            </div>

            <div class="pt-4 border-t border-scholar">
              <Button variant="outline" size="sm" as-child class="w-full border-scholar hover:bg-warning/5 text-xs font-bold uppercase tracking-tight h-9">
                <router-link to="/conflicts" class="inline-flex items-center">
                  <Eye class="h-3.5 w-3.5 mr-2" />
                  Access Conflict Repository
                </router-link>
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>

      <!-- IRR Detailed Metrics -->
      <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <!-- Cohen's Kappa by Reviewer Pair -->
        <div class="lg:col-span-2">
          <Card class="border-scholar shadow-scholar">
            <CardHeader class="border-b border-scholar py-4 bg-off-white">
              <div class="flex items-center gap-2">
                <Users class="h-4 w-4 text-deep-navy" />
                <h5 class="text-[10px] font-bold uppercase tracking-widest text-deep-navy">Inter-Rater Concordance Detail</h5>
              </div>
            </CardHeader>
            <CardContent class="p-0">
              <div v-if="irrMetrics && irrMetrics.length > 0">
                <Table>
                  <TableHeader>
                    <TableRow class="bg-cool-grey-light/20 hover:bg-cool-grey-light/20">
                      <TableHead class="text-[9px] font-bold uppercase tracking-tight py-4 px-6">Peer Pairing</TableHead>
                      <TableHead class="text-center text-[9px] font-bold uppercase tracking-tight py-4">Kappa (&kappa;)</TableHead>
                      <TableHead class="text-center text-[9px] font-bold uppercase tracking-tight py-4">Observed %</TableHead>
                      <TableHead class="text-center text-[9px] font-bold uppercase tracking-tight py-4">Analyzed Records</TableHead>
                      <TableHead class="text-[9px] font-bold uppercase tracking-tight py-4 pr-6">Methodological Interpret.</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    <TableRow v-for="metric in irrMetrics" :key="metric.id" class="border-b border-scholar last:border-0 hover:bg-off-white transition-colors">
                      <TableCell class="py-4 px-6">
                        <span class="text-sm font-semibold text-foreground">{{ getReviewerPairName(metric) }}</span>
                      </TableCell>
                      <TableCell class="text-center py-4">
                        <span :class="getKappaColorClass(metric.cohens_kappa)" class="text-base font-bold">
                          {{ formatKappa(metric.cohens_kappa) }}
                        </span>
                        <span v-if="metric.cohens_kappa < 0.70" class="ml-1.5" title="Below Cochrane threshold (0.70)">
                          <AlertTriangle class="h-3.5 w-3.5 text-warning inline align-text-bottom" />
                        </span>
                      </TableCell>
                      <TableCell class="text-center py-4 font-mono text-xs">{{ metric.percentage_agreement?.toFixed(1) }}%</TableCell>
                      <TableCell class="text-center py-4">
                        <div class="text-sm font-bold">{{ metric.total_comparisons }}</div>
                        <div class="text-[9px] text-muted-foreground uppercase tracking-tighter">{{ metric.agreements }} Agr. / {{ metric.disagreements }} Dis.</div>
                      </TableCell>
                      <TableCell class="py-4 pr-6">
                        <Badge :variant="getKappaBadgeVariant(metric.cohens_kappa)" class="uppercase text-[8px] font-bold tracking-widest">
                          {{ getKappaInterpretation(metric.cohens_kappa) }}
                        </Badge>
                      </TableCell>
                    </TableRow>
                  </TableBody>
                </Table>
              </div>
              <div v-else class="text-center py-16 space-y-4">
                <TrendingDown class="h-12 w-12 mx-auto text-muted-foreground/30" />
                <div class="space-y-1">
                  <p class="text-xs font-bold uppercase tracking-widest text-muted-foreground">Insufficient Data for IRR Calculation</p>
                  <p class="text-[10px] text-muted-foreground font-serif italic">Concordance metrics require completed dual-screening pairings.</p>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        <!-- Agreement Matrix -->
        <div>
          <Card class="border-scholar shadow-scholar overflow-hidden h-full">
            <CardHeader class="border-b border-scholar py-4 bg-off-white">
              <div class="flex items-center gap-2">
                <Grid3X3 class="h-4 w-4 text-deep-navy" />
                <h5 class="text-[10px] font-bold uppercase tracking-widest text-deep-navy">Matrix of Agreement</h5>
              </div>
            </CardHeader>
            <CardContent class="py-6 px-4">
              <div v-if="irrMetrics && irrMetrics.length > 0">
                <div v-for="metric in irrMetrics" :key="'matrix-' + metric.id" class="space-y-4 mb-8 last:mb-0">
                  <h6 class="text-[9px] font-bold uppercase tracking-widest text-muted-foreground border-b border-scholar/50 pb-2">
                    Pair: {{ getReviewerPairName(metric) }}
                  </h6>
                  <div class="grid grid-cols-2 gap-2">
                    <div class="p-3 bg-success/5 border border-success/10 rounded group hover:bg-success/10 transition-colors">
                      <p class="text-[8px] font-bold text-success uppercase tracking-widest mb-1 italic">Concordant Include</p>
                      <p class="text-2xl font-bold text-success-dark">{{ calculateBothInclude(metric) }}</p>
                    </div>
                    <div class="p-3 bg-red-800/5 border border-red-800/10 rounded group hover:bg-red-800/10 transition-colors">
                      <p class="text-[8px] font-bold text-red-800 uppercase tracking-widest mb-1 italic">Concordant Exclude</p>
                      <p class="text-2xl font-bold text-red-900">{{ calculateBothExclude(metric) }}</p>
                    </div>
                  </div>
                  <div class="p-3 bg-warning/5 border border-warning/10 rounded hover:bg-warning/10 transition-colors">
                    <div class="flex justify-between items-end">
                      <div>
                        <p class="text-[8px] font-bold text-warning-dark uppercase tracking-widest mb-1 italic">Inter-rater Disagreements</p>
                        <p class="text-2xl font-bold text-warning-dark">{{ metric.disagreements }}</p>
                      </div>
                      <AlertTriangle class="h-5 w-5 text-warning/50 mb-1" />
                    </div>
                  </div>
                </div>
              </div>
              <div v-else class="text-center py-16">
                <Grid3X3 class="h-10 w-10 mx-auto text-muted-foreground/30 mb-4" />
                <p class="text-[9px] font-bold uppercase tracking-widest text-muted-foreground">Matrix Awaiting Dual Input</p>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>

      <!-- IRR Trend Chart -->
      <Card class="border-scholar shadow-scholar overflow-hidden">
        <CardHeader class="border-b border-scholar py-4 bg-off-white">
          <div class="flex items-center gap-2">
            <TrendingUp class="h-4 w-4 text-deep-navy" />
            <h5 class="text-[10px] font-bold uppercase tracking-widest text-deep-navy">Historical Reliability Trend</h5>
          </div>
        </CardHeader>
        <CardContent class="p-8">
          <div v-if="irrTrend && irrTrend.length > 0" class="relative h-[300px]">
            <Line :data="chartData" :options="chartOptions" />
          </div>
          <div v-else class="text-center py-16 space-y-4">
            <TrendingDown class="h-12 w-12 mx-auto text-muted-foreground/30" />
            <p class="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Insufficient Longitudinal Data</p>
            <p class="text-[10px] text-muted-foreground font-serif italic">Trend indicators require multiple screening iterations.</p>
          </div>
        </CardContent>
      </Card>

      <!-- Reviewer performance & Blinding -->
      <Card class="border-scholar shadow-scholar overflow-hidden">
        <CardHeader class="border-b border-scholar py-4 bg-off-white">
          <div class="flex items-center justify-between">
            <div class="flex items-center gap-2">
              <Users class="h-4 w-4 text-deep-navy" />
              <h5 class="text-[10px] font-bold uppercase tracking-widest text-deep-navy">Reviewer Performance & Protocol Blinding</h5>
            </div>
            <div v-if="isBlinded" class="flex items-center gap-1.5 px-2 py-0.5 bg-deep-navy/10 text-deep-navy rounded border border-deep-navy/20 text-[9px] font-bold uppercase tracking-tight">
              <EyeOff class="h-3 w-3" /> PRISMA Blinding Active
            </div>
          </div>
        </CardHeader>
        <CardContent class="p-0">
          <div v-if="reviewerProgress && reviewerProgress.length > 0">
            <Table>
              <TableHeader>
                <TableRow class="bg-cool-grey-light/20 hover:bg-cool-grey-light/20">
                  <TableHead class="text-[9px] font-bold uppercase tracking-tight py-4 px-6">Investigator</TableHead>
                  <TableHead class="text-center text-[9px] font-bold uppercase tracking-tight py-4">Total Scanned</TableHead>
                  <TableHead class="text-[9px] font-bold uppercase tracking-tight py-4">Saturation</TableHead>
                  <TableHead class="text-center text-[9px] font-bold uppercase tracking-tight py-4">Conflict Load</TableHead>
                  <TableHead class="text-right text-[9px] font-bold uppercase tracking-tight py-4 pr-6">Mean Temporal Velocity</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                <TableRow v-for="(reviewer, index) in reviewerProgress" :key="reviewer.reviewer.id" class="border-b border-scholar last:border-0 hover:bg-off-white transition-colors">
                  <TableCell class="py-4 px-6">
                    <div class="flex items-center gap-2">
                      <span class="text-sm font-bold text-foreground">{{ getReviewerDisplayName(reviewer, index) }}</span>
                    </div>
                  </TableCell>
                  <TableCell class="text-center py-4 font-mono text-xs">{{ reviewer.decisions_count }}</TableCell>
                  <TableCell class="py-4 min-w-[150px]">
                    <div class="flex items-center gap-3">
                      <Progress :model-value="calculateReviewerProgress(reviewer)" class="h-1.5 flex-1 bg-cool-grey-light" />
                      <span class="text-[10px] font-bold font-mono">{{ calculateReviewerProgress(reviewer) }}%</span>
                    </div>
                  </TableCell>
                  <TableCell class="text-center py-4">
                    <span class="px-2 py-0.5 bg-warning/10 text-warning-dark border border-warning/20 rounded font-mono text-xs font-bold">
                      {{ reviewer.conflicts_involved || reviewer.conflicts_count }}
                    </span>
                  </TableCell>
                  <TableCell class="text-right py-4 pr-6 font-mono text-[11px] text-muted-foreground">
                    {{ formatAvgTime(reviewer.avg_time_seconds) }}
                  </TableCell>
                </TableRow>
              </TableBody>
            </Table>
          </div>
          <div v-else class="text-center py-16">
            <Users class="h-10 w-10 mx-auto text-muted-foreground/30 mb-4" />
            <p class="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Awaiting Reviewer Participation</p>
          </div>
        </CardContent>
      </Card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue';
import { Line } from 'vue-chartjs';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  Filler,
} from 'chart.js';
import { useConflictSSE } from '../composables/useConflictSSE';
import { useTeamDashboard } from '../composables/useTeamDashboard';

// Lucide icons
import {
  RefreshCw,
  AlertTriangle,
  AlertCircle,
  TrendingUp,
  TrendingDown,
  ClipboardCheck,
  Eye,
  EyeOff,
  Users,
  Grid3X3,
  ShieldCheck,
} from 'lucide-vue-next';

// Shadcn-vue components
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';

// Agent Grey components
import { LoadingState } from '@/components/ui/loading-state';
import { ErrorAlert } from '@/components/shared';

// Register Chart.js components
ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  Filler
);

// Composable: all state, computed, and methods
const {
  isLoading,
  error,
  stats,
  irrTrend,
  irrMetrics,
  reviewerProgress,
  blindingError,
  sessionId,
  progressPercentage,
  cohensKappa,
  percentageAgreement,
  kappaInterpretation,
  kappaColorClass,
  kappaBadgeVariant,
  isBlinded,
  chartData,
  chartOptions,
  loadDashboard,
  handleRefresh,
  formatKappa,
  calculateReviewerProgress,
  formatAvgTime,
  getReviewerDisplayName,
  getReviewerPairName,
  getKappaInterpretation,
  getKappaColorClass,
  getKappaBadgeVariant,
  calculateBothInclude,
  calculateBothExclude,
  handleConflictEvent,
  handleConsensusEvent,
  handleIRREvent,
} = useTeamDashboard();

// SSE connection for real-time updates
const { isConnected, connect, disconnect } = useConflictSSE(sessionId.value);

// Lifecycle
onMounted(() => {
  loadDashboard();

  if (sessionId.value) {
    connect();
    window.addEventListener('conflict:conflict_detected', handleConflictEvent);
    window.addEventListener('conflict:consensus_reached', handleConsensusEvent);
    window.addEventListener('conflict:irr_calculated', handleIRREvent);
  }
});

onUnmounted(() => {
  disconnect();
  window.removeEventListener('conflict:conflict_detected', handleConflictEvent);
  window.removeEventListener('conflict:consensus_reached', handleConsensusEvent);
  window.removeEventListener('conflict:irr_calculated', handleIRREvent);
});
</script>
