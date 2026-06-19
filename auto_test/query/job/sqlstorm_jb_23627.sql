WITH RecursiveActorCount AS (
    SELECT 
        c.movie_id,
        COUNT(DISTINCT c.person_id) AS actor_count
    FROM 
        cast_info c
    GROUP BY 
        c.movie_id
),
MovieInfoDetail AS (
    SELECT 
        m.id AS movie_id,
        m.title,
        COALESCE(mi.info, 'No Information') AS movie_info,
        k.keyword,
        co.name AS company_name,
        ct.kind AS company_type,
        ROW_NUMBER() OVER (PARTITION BY m.id ORDER BY k.keyword) AS keyword_rank
    FROM 
        aka_title m
    LEFT JOIN 
        movie_info mi ON m.id = mi.movie_id
    LEFT JOIN 
        movie_keyword mk ON mk.movie_id = m.id
    LEFT JOIN 
        keyword k ON k.id = mk.keyword_id
    LEFT JOIN 
        movie_companies mc ON mc.movie_id = m.id
    LEFT JOIN 
        company_name co ON co.id = mc.company_id
    LEFT JOIN 
        company_type ct ON ct.id = mc.company_type_id
    WHERE 
        m.production_year > 2000
),
ExtendedMovieInfo AS (
    SELECT 
        m.title,
        m.movie_info,
        m.keyword,
        m.company_name,
        m.company_type,
        ac.actor_count
    FROM 
        MovieInfoDetail m
    JOIN 
        RecursiveActorCount ac ON m.movie_id = ac.movie_id
),
FilteredMovies AS (
    SELECT 
        em.*,
        CASE 
            WHEN em.keyword IS NOT NULL THEN em.keyword 
            ELSE 'Unknown' 
        END AS keyword_final,
        EXTRACT(YEAR FROM cast('2024-10-01' as date)) - m.production_year AS age_of_movie
    FROM 
        ExtendedMovieInfo em
    JOIN 
        aka_title m ON em.title = m.title
    WHERE 
        em.actor_count > 5 
        AND (em.company_type IS NOT NULL OR em.company_name IS NOT NULL)
)
SELECT 
    title,
    movie_info,
    keyword_final,
    company_name,
    COALESCE(company_type, 'Independent') AS company_type,
    age_of_movie
FROM 
    FilteredMovies
WHERE 
    age_of_movie > 10;
