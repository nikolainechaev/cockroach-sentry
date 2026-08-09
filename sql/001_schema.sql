-- ============================================
-- Cockroach Sentry — schema v1 (multi-species)
-- ============================================

CREATE TABLE IF NOT EXISTS detections (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  detected_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  camera_id TEXT NOT NULL DEFAULT 'cam-kitchen-1',
  zone TEXT NOT NULL,
  species TEXT NOT NULL DEFAULT 'unknown',      -- cockroach | ladybug | cicada | fly | unknown
  species_confidence FLOAT,
  x INT, y INT,
  confidence FLOAT,
  track_id UUID,
  snapshot_s3_key TEXT,
  ambient_temp FLOAT,
  ambient_humidity FLOAT,
  lights_on BOOL,
  INDEX idx_detections_time (detected_at),
  INDEX idx_detections_zone (zone, detected_at),
  INDEX idx_detections_species (species, detected_at)
);

CREATE TABLE IF NOT EXISTS observations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  summary TEXT NOT NULL,
  embedding VECTOR(1024),
  source_track_id UUID,
  species TEXT,
  zone TEXT
);

CREATE TABLE IF NOT EXISTS hypotheses (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  statement TEXT NOT NULL,
  species TEXT,
  confidence FLOAT NOT NULL DEFAULT 0.5,
  evidence_count INT NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  superseded_by UUID REFERENCES hypotheses(id),
  valid BOOL NOT NULL DEFAULT true,
  INDEX idx_hypotheses_valid (valid) WHERE valid = true
);

CREATE TABLE IF NOT EXISTS interventions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  action TEXT NOT NULL,
  taken_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  hypothesis_id UUID REFERENCES hypotheses(id),
  outcome TEXT,
  effective BOOL
);

CREATE TABLE IF NOT EXISTS zone_stats (
  zone TEXT NOT NULL,
  night DATE NOT NULL,
  species TEXT NOT NULL DEFAULT 'all',
  detection_count INT NOT NULL DEFAULT 0,
  avg_temp FLOAT,
  avg_humidity FLOAT,
  PRIMARY KEY (zone, night, species)
);