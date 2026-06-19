
WITH RankedTitles AS (
    SELECT 
        t.id AS title_id,
        t.title,
        t.production_year,
        ROW_NUMBER() OVER (PARTITION BY t.production_year ORDER BY t.title) AS title_rank
    FROM 
        title t
    WHERE 
        t.production_year IS NOT NULL
),
ActorDetails AS (
    SELECT 
        ak.name AS actor_name,
        p.gender,
        p.id AS person_id,
        ROW_NUMBER() OVER (PARTITION BY ak.person_id ORDER BY ak.name) AS actor_rank
    FROM 
        aka_name ak
    JOIN 
        name p ON ak.person_id = p.imdb_id
),
MovieKeywords AS (
    SELECT 
        m.id AS movie_id,
        STRING_AGG(k.keyword, ', ') AS keywords
    FROM 
        movie_keyword mk
    JOIN 
        keyword k ON mk.keyword_id = k.id
    JOIN 
        title m ON mk.movie_id = m.id
    GROUP BY 
        m.id
),
TitleWithKeywords AS (
    SELECT 
        rt.title_id,
        rt.title,
        rt.production_year,
        mk.keywords
    FROM 
        RankedTitles rt
    LEFT JOIN 
        MovieKeywords mk ON rt.title_id = mk.movie_id
)

SELECT 
    tt.title,
    tt.production_year,
    tt.keywords,
    ad.actor_name,
    ad.gender
FROM 
    TitleWithKeywords tt
LEFT JOIN 
    ActorDetails ad ON EXISTS (
        SELECT 1
        FROM cast_info ci
        WHERE ci.movie_id = tt.title_id 
          AND ci.person_id = ad.person_id
          AND ci.nr_order = 1
    )
WHERE 
    tt.production_year >= 2000;
