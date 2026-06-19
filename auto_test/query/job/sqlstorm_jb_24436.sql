
WITH RecursiveMovieCTE AS (
    SELECT 
        t.id AS movie_id,
        t.title,
        t.production_year,
        t.kind_id,
        COALESCE(ak.name, 'Unknown') AS main_actor,
        COUNT(DISTINCT mc.company_id) AS company_count,
        ROW_NUMBER() OVER (PARTITION BY t.production_year ORDER BY t.title) AS movie_rank
    FROM 
        aka_title t
    LEFT JOIN 
        cast_info ci ON ci.movie_id = t.movie_id 
    LEFT JOIN 
        aka_name ak ON ak.person_id = ci.person_id
    LEFT JOIN 
        movie_companies mc ON mc.movie_id = t.movie_id
    WHERE 
        t.production_year IS NOT NULL
    GROUP BY 
        t.id, t.title, t.production_year, t.kind_id, ak.name
), FilteredMovies AS (
    SELECT 
        *,
        CASE 
            WHEN company_count > 10 THEN 'Large Production'
            WHEN company_count BETWEEN 5 AND 10 THEN 'Medium Production'
            ELSE 'Small Production'
        END AS production_scale
    FROM 
        RecursiveMovieCTE
    WHERE 
        main_actor IS NOT NULL
    AND 
        movie_rank <= 50
), TopMovies AS (
    SELECT 
        *,
        LAG(main_actor) OVER (ORDER BY movie_id) AS previous_actor,
        LEAD(title) OVER (ORDER BY movie_id) AS next_movie
    FROM 
        FilteredMovies
)
SELECT 
    tm.movie_id,
    tm.title,
    tm.production_year,
    tm.main_actor,
    tm.production_scale,
    COALESCE(tm.previous_actor, 'N/A') AS previous_actor,
    COALESCE(tm.next_movie, 'N/A') AS next_movie,
    CASE 
        WHEN tm.main_actor IS NULL THEN 'No Actor Data'
        WHEN CHAR_LENGTH(tm.title) % 2 = 0 THEN 'Even Title Length'
        ELSE 'Odd Title Length'
    END AS title_length_description
FROM 
    TopMovies tm
WHERE 
    EXISTS (
        SELECT 1
        FROM movie_info mi 
        WHERE mi.movie_id = tm.movie_id AND mi.info_type_id = 1 AND mi.info IS NOT NULL
    )
AND 
    NOT EXISTS (
        SELECT 1 
        FROM movie_keyword mk 
        WHERE mk.movie_id = tm.movie_id AND mk.keyword_id IN (
            SELECT id FROM keyword WHERE keyword LIKE '%OMNIA%'
        )
    );
