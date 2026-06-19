WITH ActorTitles AS (
    SELECT 
        ak.name AS actor_name,
        at.title AS movie_title,
        at.production_year,
        ct.kind AS company_type,
        COUNT(mk.id) AS keyword_count
    FROM 
        aka_name ak
    JOIN 
        cast_info ci ON ak.person_id = ci.person_id
    JOIN 
        aka_title at ON ci.movie_id = at.id
    LEFT JOIN 
        movie_keyword mk ON at.id = mk.movie_id
    LEFT JOIN 
        movie_companies mc ON at.id = mc.movie_id
    LEFT JOIN 
        company_type ct ON mc.company_type_id = ct.id
    GROUP BY 
        ak.name, at.title, at.production_year, ct.kind
),
RankedFilms AS (
    SELECT 
        actor_name,
        movie_title,
        production_year,
        company_type,
        keyword_count,
        RANK() OVER (PARTITION BY actor_name ORDER BY production_year DESC, keyword_count DESC) AS film_rank
    FROM 
        ActorTitles
)
SELECT 
    actor_name,
    movie_title,
    production_year,
    company_type,
    keyword_count
FROM 
    RankedFilms
WHERE 
    film_rank <= 5;
