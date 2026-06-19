
WITH RankedMovies AS (
    SELECT 
        t.id AS title_id,
        t.title,
        t.production_year,
        a.name AS actor_name,
        ct.kind AS company_type,
        STRING_AGG(DISTINCT kw.keyword, ', ' ORDER BY kw.keyword) AS keywords,
        ROW_NUMBER() OVER (PARTITION BY t.id ORDER BY a.name) AS actor_rank
    FROM 
        aka_title t
    JOIN 
        complete_cast cc ON t.id = cc.movie_id
    JOIN 
        cast_info ci ON ci.movie_id = t.id AND ci.person_id = cc.subject_id
    JOIN 
        aka_name a ON a.person_id = ci.person_id
    JOIN 
        movie_companies mc ON mc.movie_id = t.id
    JOIN 
        company_type ct ON mc.company_type_id = ct.id
    LEFT JOIN 
        movie_keyword mk ON mk.movie_id = t.id
    LEFT JOIN 
        keyword kw ON kw.id = mk.keyword_id
    WHERE 
        t.production_year >= 2000
    GROUP BY 
        t.id, t.title, t.production_year, a.name, ct.kind
),
FilteredMovies AS (
    SELECT 
        title_id, title, production_year, actor_name, company_type, keywords
    FROM 
        RankedMovies
    WHERE 
        actor_rank <= 3
)
SELECT 
    fm.title AS Movie_Title,
    fm.production_year AS Production_Year,
    fm.actor_name AS Leading_Actor,
    fm.company_type AS Company_Type,
    fm.keywords AS Associated_Keywords
FROM 
    FilteredMovies fm;
