WITH RankedTitles AS (
    SELECT 
        t.id AS title_id,
        t.title,
        t.production_year,
        ROW_NUMBER() OVER (PARTITION BY t.production_year ORDER BY t.production_year DESC) AS year_rank
    FROM 
        title t
    WHERE 
        t.production_year IS NOT NULL
),
TopCast AS (
    SELECT 
        ci.movie_id,
        a.name AS actor_name,
        RANK() OVER (PARTITION BY ci.movie_id ORDER BY ci.nr_order) AS actor_rank
    FROM 
        cast_info ci
    JOIN 
        aka_name a ON ci.person_id = a.person_id
    WHERE 
        a.name IS NOT NULL
),
MovieInfoAggregated AS (
    SELECT 
        mc.movie_id,
        STRING_AGG(DISTINCT mi.info, ', ') AS info_text
    FROM 
        movie_info mi
    JOIN 
        movie_companies mc ON mi.movie_id = mc.movie_id
    WHERE 
        mi.info_type_id IN (SELECT id FROM info_type WHERE info = 'Summary')
    GROUP BY 
        mc.movie_id
)
SELECT 
    t.title,
    t.production_year,
    tc.actor_name,
    mia.info_text
FROM 
    RankedTitles t
LEFT JOIN 
    TopCast tc ON t.title_id = tc.movie_id AND tc.actor_rank <= 3
LEFT JOIN 
    MovieInfoAggregated mia ON t.title_id = mia.movie_id
WHERE 
    t.year_rank <= 10;
