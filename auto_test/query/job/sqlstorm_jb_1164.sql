
WITH MovieDetails AS (
    SELECT 
        a.title AS movie_title,
        a.production_year,
        COALESCE(k.keyword, 'No Keywords') AS keyword,
        COUNT(DISTINCT ci.person_id) AS cast_count
    FROM 
        aka_title a
    LEFT JOIN 
        movie_keyword mk ON a.id = mk.movie_id
    LEFT JOIN 
        keyword k ON mk.keyword_id = k.id
    LEFT JOIN 
        complete_cast cc ON a.id = cc.movie_id
    LEFT JOIN 
        cast_info ci ON cc.subject_id = ci.person_id
    GROUP BY 
        a.title, a.production_year, k.keyword
),
ActorDetails AS (
    SELECT 
        ak.name AS actor_name,
        ci.movie_id,
        ROW_NUMBER() OVER (PARTITION BY ci.movie_id ORDER BY ci.nr_order) AS actor_order
    FROM 
        aka_name ak
    JOIN 
        cast_info ci ON ak.person_id = ci.person_id
),
RankedMovies AS (
    SELECT 
        md.movie_title,
        md.production_year,
        md.keyword,
        md.cast_count,
        ROW_NUMBER() OVER (ORDER BY md.production_year DESC, md.cast_count DESC) AS rank
    FROM 
        MovieDetails md
)
SELECT 
    rm.movie_title,
    rm.production_year,
    rm.keyword,
    rm.cast_count,
    ad.actor_name,
    ad.actor_order
FROM 
    RankedMovies rm
LEFT JOIN 
    ActorDetails ad ON rm.movie_title = ad.actor_name
WHERE 
    rm.rank <= 10 AND 
    (rm.keyword IS NOT NULL OR rm.cast_count > 0);
