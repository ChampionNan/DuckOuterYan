
WITH MovieDetails AS (
    SELECT 
        t.id AS title_id, 
        t.title, 
        t.production_year, 
        ak.name AS actor_name,
        ci.nr_order, 
        c.kind AS comp_cast_kind,
        STRING_AGG(DISTINCT kw.keyword, ', ') AS keywords
    FROM 
        title t
    JOIN 
        complete_cast cc ON t.id = cc.movie_id
    JOIN 
        cast_info ci ON ci.movie_id = cc.movie_id
    JOIN 
        aka_name ak ON ak.person_id = ci.person_id
    JOIN 
        movie_companies mc ON mc.movie_id = t.id
    JOIN 
        company_name cn ON cn.id = mc.company_id
    JOIN 
        comp_cast_type c ON c.id = ci.person_role_id
    LEFT JOIN 
        movie_keyword mk ON mk.movie_id = t.id
    LEFT JOIN 
        keyword kw ON kw.id = mk.keyword_id
    WHERE 
        t.production_year >= 2000 
        AND ci.nr_order <= 5
    GROUP BY 
        t.id, t.title, t.production_year, ak.name, ci.nr_order, c.kind
),
RankedMovies AS (
    SELECT 
        md.*, 
        ROW_NUMBER() OVER (PARTITION BY md.production_year ORDER BY md.title) AS year_rank
    FROM 
        MovieDetails md
)
SELECT 
    title, 
    production_year, 
    actor_name, 
    nr_order, 
    comp_cast_kind, 
    keywords
FROM 
    RankedMovies
WHERE 
    year_rank <= 10;
