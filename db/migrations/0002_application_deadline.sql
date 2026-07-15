-- 0002_application_deadline.sql — nullable application deadline for the tracker page.

ALTER TABLE job ADD COLUMN application_deadline TEXT;
