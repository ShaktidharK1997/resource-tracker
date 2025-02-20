BEGIN;

-- Add deleted columns to floating_ips
ALTER TABLE floating_ips 
    ADD COLUMN IF NOT EXISTS user_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS system_deleted BOOLEAN NOT NULL DEFAULT FALSE;

-- Create project_site enum
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'project_site') THEN
        CREATE TYPE project_site AS ENUM ('kvm@tacc', 'chi@uc', 'chi@tacc');
    END IF;
END $$;

-- Add project_site column to all relevant compute tables 
-- !!NOTE : Please change kvm@tacc to the project-site that you are currently tracking compute resources for 
DO $$
DECLARE
    compute_tables text[] := ARRAY['servers', 'networks', 'routers', 'subnets', 'floating_ips'];
    t text;
BEGIN
    FOREACH t IN ARRAY compute_tables LOOP
        EXECUTE format('
            ALTER TABLE %I 
            ADD COLUMN IF NOT EXISTS project_site project_site;
            
            UPDATE %I 
            SET project_site = ''kvm@tacc'' 
            WHERE project_site IS NULL;
            
            ALTER TABLE %I 
            ALTER COLUMN project_site SET NOT NULL;
        ', t, t, t);
    END LOOP;
END $$;

-- Add project_site column to all relevant lease tables 
-- !!NOTE : Please change kvm@tacc to the project-site that you are currently tracking compute resources for 
DO $$
DECLARE
    gpu_tables text[] := ARRAY['gpu_leases', 'gpu_lease_reservations'];
    t text;
BEGIN
    FOREACH t IN ARRAY gpu_tables LOOP
        EXECUTE format('
            ALTER TABLE %I 
            ADD COLUMN IF NOT EXISTS project_site project_site;
            
            UPDATE %I 
            SET project_site = ''kvm@tacc'' 
            WHERE project_site IS NULL;
            
            ALTER TABLE %I 
            ALTER COLUMN project_site SET NOT NULL;
        ', t, t, t);
    END LOOP;
END $$;

COMMIT;