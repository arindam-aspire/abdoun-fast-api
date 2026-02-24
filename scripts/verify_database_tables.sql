-- Database Verification Queries
-- Run these in pgAdmin to check your database state

-- 1. Check current database and schema
SELECT current_database(), current_schema();

-- 2. Check if table exists in public schema
SELECT table_name, table_schema 
FROM information_schema.tables 
WHERE table_name = 'properties_normalized';

-- 3. List all tables in public schema
SELECT table_name 
FROM information_schema.tables 
WHERE table_schema = 'public' 
ORDER BY table_name;

-- 4. Check properties count (use fully qualified name)
SELECT COUNT(*) FROM public.properties_normalized;

-- 5. Check a sample property
SELECT id, title, url 
FROM public.properties_normalized 
LIMIT 5;

-- 6. Check property features count
SELECT COUNT(*) FROM public.property_features;

-- 7. Check all table counts
SELECT 
    'property_categories' as table_name, COUNT(*) as count FROM public.property_categories
UNION ALL
SELECT 'property_types', COUNT(*) FROM public.property_types
UNION ALL
SELECT 'cities', COUNT(*) FROM public.cities
UNION ALL
SELECT 'areas', COUNT(*) FROM public.areas
UNION ALL
SELECT 'property_status', COUNT(*) FROM public.property_status
UNION ALL
SELECT 'features', COUNT(*) FROM public.features
UNION ALL
SELECT 'search_fields', COUNT(*) FROM public.search_fields
UNION ALL
SELECT 'category_features', COUNT(*) FROM public.category_features
UNION ALL
SELECT 'type_features', COUNT(*) FROM public.type_features
UNION ALL
SELECT 'category_search_fields', COUNT(*) FROM public.category_search_fields
UNION ALL
SELECT 'properties_normalized', COUNT(*) FROM public.properties_normalized
UNION ALL
SELECT 'property_features', COUNT(*) FROM public.property_features;

