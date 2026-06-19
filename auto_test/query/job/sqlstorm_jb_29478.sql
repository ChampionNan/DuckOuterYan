WITH RankedMovies AS (
    SELECT 
        m.id AS movie_id,
        m.title,
        m.production_year,
        ROW_NUMBER() OVER (PARTITION BY m.production_year ORDER BY m.title) as rank
    FROM title m
    WHERE m.production_year IS NOT NULL
),
ActorDetails AS (
    SELECT 
        a.name AS actor_name,
        a.md5sum AS actor_md5,
        c.movie_id,
        c.nr_order
    FROM cast_info c
    JOIN aka_name a ON c.person_id = a.person_id
    WHERE c.note IS NULL
),
MovieKeywords AS (
    SELECT 
        mk.movie_id,
        STRING_AGG(k.keyword, ', ') AS keywords
    FROM movie_keyword mk
    JOIN keyword k ON mk.keyword_id = k.id
    GROUP BY mk.movie_id
)
SELECT 
    rm.movie_id,
    rm.title,
    rm.production_year,
    ad.actor_name,
    ad.actor_md5,
    mk.keywords
FROM RankedMovies rm
LEFT JOIN ActorDetails ad ON rm.movie_id = ad.movie_id
LEFT JOIN MovieKeywords mk ON rm.movie_id = mk.movie_id
WHERE rm.rank <= 5;
