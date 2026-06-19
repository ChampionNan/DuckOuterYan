WITH MovieDetails AS (
    SELECT 
        t.id AS movie_id,
        t.title,
        t.production_year,
        c.name AS company_name,
        k.keyword AS movie_keyword,
        p.info AS person_info,
        COUNT(DISTINCT ca.person_id) AS cast_count
    FROM 
        aka_title t
    JOIN 
        movie_companies mc ON t.id = mc.movie_id
    JOIN 
        company_name c ON mc.company_id = c.id
    JOIN 
        movie_keyword mk ON t.id = mk.movie_id
    JOIN 
        keyword k ON mk.keyword_id = k.id
    LEFT JOIN 
        complete_cast cc ON t.id = cc.movie_id
    LEFT JOIN 
        cast_info ca ON cc.id = ca.movie_id
    LEFT JOIN 
        person_info p ON ca.person_id = p.person_id
    WHERE 
        t.production_year >= 2000 AND
        t.kind_id IN (SELECT id FROM kind_type WHERE kind LIKE '%feature%')
    GROUP BY 
        t.id, t.title, t.production_year, c.name, k.keyword, p.info
),
Ranking AS (
    SELECT 
        movie_id,
        title,
        production_year,
        company_name,
        movie_keyword,
        person_info,
        cast_count,
        RANK() OVER (PARTITION BY production_year ORDER BY cast_count DESC) AS rank
    FROM 
        MovieDetails
)
SELECT 
    rank,
    title,
    production_year,
    company_name,
    movie_keyword,
    person_info,
    cast_count
FROM 
    Ranking
WHERE 
    rank <= 10;
