
WITH MovieDetails AS (
    SELECT 
        t.title AS movie_title,
        t.production_year,
        k.keyword AS movie_keyword,
        cn.name AS company_name,
        ct.kind AS company_type,
        ARRAY_AGG(DISTINCT n.name ORDER BY n.name) AS cast_names
    FROM 
        aka_title t
    JOIN 
        movie_keyword mk ON t.id = mk.movie_id
    JOIN 
        keyword k ON mk.keyword_id = k.id
    JOIN 
        movie_companies mc ON t.id = mc.movie_id
    JOIN 
        company_name cn ON mc.company_id = cn.id
    JOIN 
        company_type ct ON mc.company_type_id = ct.id
    LEFT JOIN 
        complete_cast cc ON t.id = cc.movie_id
    LEFT JOIN 
        cast_info ci ON cc.subject_id = ci.person_id
    LEFT JOIN 
        aka_name n ON ci.person_id = n.person_id
    GROUP BY 
        t.title, t.production_year, k.keyword, cn.name, ct.kind
),
RankedMovies AS (
    SELECT 
        movie_title,
        production_year,
        movie_keyword,
        company_name,
        company_type,
        cast_names,
        ROW_NUMBER() OVER (PARTITION BY movie_keyword ORDER BY production_year DESC) AS rank
    FROM 
        MovieDetails
)
SELECT 
    movie_title,
    production_year,
    movie_keyword,
    company_name,
    company_type,
    cast_names
FROM 
    RankedMovies
WHERE 
    rank <= 5;
