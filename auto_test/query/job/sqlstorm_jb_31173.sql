WITH RECURSIVE MovieHierarchy AS (
    
    SELECT 
        T.id AS movie_id,
        T.title,
        T.production_year,
        T.episode_of_id,
        0 AS level
    FROM 
        title T
    WHERE 
        T.episode_of_id IS NULL

    UNION ALL

    SELECT 
        T.id AS movie_id,
        T.title,
        T.production_year,
        T.episode_of_id,
        MH.level + 1
    FROM 
        title T
    JOIN 
        MovieHierarchy MH ON T.episode_of_id = MH.movie_id
),
ActorsInfo AS (
    
    SELECT 
        A.id AS actor_id,
        A.name,
        A.imdb_index,
        P.info AS age,
        COUNT(CI.movie_id) AS movie_count
    FROM 
        aka_name A
    LEFT JOIN 
        cast_info CI ON A.person_id = CI.person_id
    LEFT JOIN 
        person_info P ON A.person_id = P.person_id AND P.info_type_id = (SELECT id FROM info_type WHERE info = 'age')
    GROUP BY 
        A.id, A.name, A.imdb_index, P.info
),
FilteredTitles AS (
    
    SELECT 
        T.id,
        T.title,
        T.production_year,
        K.keyword AS keyword_used
    FROM 
        title T
    JOIN 
        movie_keyword MK ON T.id = MK.movie_id
    JOIN 
        keyword K ON MK.keyword_id = K.id
    WHERE 
        T.production_year > 2000 AND 
        (K.keyword LIKE '%action%' OR K.keyword LIKE '%drama%')
),
Ranking AS (
    
    SELECT 
        F.id,
        F.title,
        F.production_year,
        RANK() OVER (ORDER BY F.production_year DESC) AS year_rank
    FROM 
        FilteredTitles F
)
SELECT 
    R.title,
    R.production_year,
    R.year_rank,
    AI.name AS actor_name,
    AI.age,
    AI.movie_count,
    MH.level AS episode_level,
    COALESCE(MH.title, 'Standalone Movie') AS episode_of
FROM 
    Ranking R
LEFT JOIN 
    movie_companies MC ON R.id = MC.movie_id
LEFT JOIN 
    company_name CN ON MC.company_id = CN.id
LEFT JOIN 
    ActorsInfo AI ON AI.actor_id = MC.company_id  
LEFT JOIN 
    MovieHierarchy MH ON R.id = MH.movie_id
WHERE 
    CN.country_code IS NULL OR CN.country_code = 'USA';
