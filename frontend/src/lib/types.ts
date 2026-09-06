// Shared frontend types mirroring the backend Prisma models (database/schema.prisma).
// Kept hand-written rather than code-generated for now — see docs/api.md.

export type CameraStatus = "ONLINE" | "OFFLINE" | "ERROR" | "PROCESSING";
export type Severity = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
export type AlertStatus = "NEW" | "REVIEWED" | "DISMISSED" | "ESCALATED";
export type IncidentStatus = "UNREVIEWED" | "UNDER_REVIEW" | "CONFIRMED" | "DISMISSED";
export type InferenceMode = "REAL" | "DEMO";

export interface Camera {
  id: string;
  name: string;
  location: string;
  streamUrl: string;
  description?: string | null;
  status: CameraStatus;
  isDemo: boolean;
  createdAt: string;
  updatedAt: string;
}

export interface Detection {
  id: string;
  cameraId: string;
  objectLabel: string;
  confidence: number;
  boundingBox: string;
  mode: InferenceMode;
  frameTimestamp: string;
  createdAt: string;
}

export interface Action {
  id: string;
  cameraId: string;
  label: string;
  confidence: number;
  description?: string | null;
  mode: InferenceMode;
  windowStart: string;
  windowEnd: string;
  threatScoreHint?: number | null;
  createdAt: string;
}

export interface Alert {
  id: string;
  cameraId: string;
  camera?: Camera;
  actionId?: string | null;
  type: string;
  severity: Severity;
  confidence: number;
  description: string;
  status: AlertStatus;
  mode: InferenceMode;
  threatScore?: number | null;
  incidentId?: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface Incident {
  id: string;
  title: string;
  eventType: string;
  severity: Severity;
  confidence: number;
  aiDescription?: string | null;
  startTime: string;
  endTime?: string | null;
  reviewStatus: IncidentStatus;
  isDemo: boolean;
  createdAt: string;
  updatedAt: string;
  alerts?: Alert[];
  videoSegments?: VideoSegment[];
}

export interface VideoSegment {
  id: string;
  cameraId: string;
  filePath: string;
  startTime: string;
  endTime?: string | null;
  isDemo: boolean;
}

export interface OverviewStats {
  totalCameras: number;
  camerasOnline: number;
  activeAlerts: number;
  incidentsToday: number;
  threatLevelSummary: Record<Severity, number>;
  recentIncidents: Incident[];
}

export interface SystemStatus {
  database: { ok: boolean };
  aiService: { reachable: boolean; detail?: string };
  camerasOnline: number;
  activeAlerts: number;
  timestamp: string;
}

export interface AnalyticsData {
  alertsOverTime: { date: string; count: number }[];
  incidentsByType: { type: string; count: number }[];
  incidentsBySeverity: { severity: string; count: number }[];
  detectionCounts: { object: string; count: number }[];
  cameraActivity: { cameraId: string; count: number }[];
  reviewStats: { status: string; count: number }[];
}

export interface User {
  id: string;
  email: string;
  name: string;
  role: string;
}
