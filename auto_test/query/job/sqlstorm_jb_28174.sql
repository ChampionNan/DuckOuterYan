WITH RankedTitle AS (
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

ActorCount AS (
    SELECT 
        c.movie_id,
        COUNT(DISTINCT c.person_id) AS actor_count
    FROM 
        cast_info c
    GROUP BY 
        c.movie_id
),

TopMovies AS (
    SELECT 
        rt.title_id,
        rt.title,
        rt.production_year,
        ac.actor_count
    FROM 
        RankedTitle rt
    JOIN 
        ActorCount ac ON rt.title_id = ac.movie_id
    WHERE 
        rt.title_rank <= 5
)

SELECT 
    tm.title,
    tm.production_year,
    tm.actor_count,
    ak.name AS actor_name,
    ak.name_pcode_nf AS actor_name_pcode_nf,
    com.name AS company_name,
    co.kind AS company_type,
    kw.keyword AS movie_keyword
FROM 
    TopMovies tm
LEFT JOIN 
    cast_info ci ON tm.title_id = ci.movie_id
LEFT JOIN 
    aka_name ak ON ci.person_id = ak.person_id 
LEFT JOIN 
    movie_companies mc ON mc.movie_id = tm.title_id
LEFT JOIN 
    company_name com ON mc.company_id = com.id
LEFT JOIN 
    company_type co ON mc.company_type_id = co.id
LEFT JOIN 
    movie_keyword mw ON tm.title_id = mw.movie_id
LEFT JOIN 
    keyword kw ON mw.keyword_id = kw.id;
