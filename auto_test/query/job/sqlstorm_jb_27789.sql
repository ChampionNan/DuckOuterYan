
WITH MovieDetails AS (
    SELECT 
        t.id AS title_id,
        t.title AS movie_title,
        t.production_year,
        k.keyword AS movie_keyword,
        c.name AS company_name,
        STRING_AGG(DISTINCT p.name, ', ' ORDER BY p.name) AS cast_names
    FROM 
        title t
    LEFT JOIN 
        movie_keyword mk ON t.id = mk.movie_id
    LEFT JOIN 
        keyword k ON mk.keyword_id = k.id
    LEFT JOIN 
        movie_companies mc ON t.id = mc.movie_id
    LEFT JOIN 
        company_name c ON mc.company_id = c.id
    LEFT JOIN 
        complete_cast cc ON t.id = cc.movie_id
    LEFT JOIN 
        cast_info ci ON cc.subject_id = ci.person_id
    LEFT JOIN 
        aka_name p ON ci.person_id = p.person_id
    WHERE 
        k.keyword IS NOT NULL
    GROUP BY 
        t.id, t.title, t.production_year, k.keyword, c.name
    ORDER BY 
        t.production_year DESC, t.title
)
SELECT 
    md.title_id,
    md.movie_title,
    md.production_year,
    md.movie_keyword,
    md.company_name,
    md.cast_names
FROM 
    MovieDetails md
WHERE 
    md.production_year > 2000
    AND md.movie_keyword LIKE '%action%';
