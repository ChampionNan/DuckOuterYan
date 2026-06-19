WITH RankedMovies AS (
    SELECT 
        at.id AS title_id,
        at.title,
        at.production_year,
        ROW_NUMBER() OVER (PARTITION BY at.production_year ORDER BY at.production_year DESC) AS rn
    FROM 
        aka_title at
    WHERE 
        at.kind_id IN (SELECT id FROM kind_type WHERE kind LIKE 'movie%')
),
TopMovies AS (
    SELECT 
        rm.title_id,
        rm.title,
        rm.production_year,
        ak.name AS actor_name,
        COUNT(DISTINCT mc.company_id) AS company_count
    FROM 
        RankedMovies rm
    LEFT JOIN 
        complete_cast cc ON rm.title_id = cc.movie_id
    LEFT JOIN 
        cast_info ci ON cc.subject_id = ci.person_id
    LEFT JOIN 
        aka_name ak ON ci.person_id = ak.person_id
    LEFT JOIN 
        movie_companies mc ON rm.title_id = mc.movie_id
    WHERE 
        rm.rn <= 10
    GROUP BY 
        rm.title_id, rm.title, rm.production_year, ak.name
),
ActorInfo AS (
    SELECT
        ak.person_id,
        ak.name,
        COALESCE(pi.info, 'No Info') AS actor_info
    FROM 
        aka_name ak
    LEFT JOIN 
        person_info pi ON ak.person_id = pi.person_id 
        AND pi.info_type_id IN (SELECT id FROM info_type WHERE info LIKE 'bio%')
)
SELECT 
    tm.title,
    tm.production_year,
    tm.actor_name,
    ai.actor_info,
    tm.company_count
FROM 
    TopMovies tm
JOIN 
    ActorInfo ai ON tm.actor_name = ai.name
WHERE 
    tm.production_year >= 2000;
