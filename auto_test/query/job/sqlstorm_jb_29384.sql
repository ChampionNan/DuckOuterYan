WITH RankedTitles AS (
    SELECT 
        a.id AS aka_id,
        a.name AS aka_name,
        a.imdb_index AS aka_imdb_index,
        t.id AS title_id,
        t.title AS movie_title,
        t.production_year,
        ROW_NUMBER() OVER (PARTITION BY a.person_id ORDER BY t.production_year DESC) AS rank
    FROM 
        aka_name a
    JOIN 
        cast_info ci ON a.person_id = ci.person_id
    JOIN 
        aka_title t ON ci.movie_id = t.movie_id
), 
PersonDetails AS (
    SELECT 
        p.id AS person_id,
        p.name AS person_name,
        pi.info AS bio_info
    FROM 
        name p
    LEFT JOIN 
        person_info pi ON p.id = pi.person_id
), 
MovieKeywords AS (
    SELECT 
        m.id AS movie_id,
        array_agg(k.keyword) AS keywords_list
    FROM 
        movie_keyword mk
    JOIN 
        keyword k ON mk.keyword_id = k.id
    JOIN 
        title m ON mk.movie_id = m.id
    GROUP BY 
        m.id
)

SELECT 
    pd.person_id,
    pd.person_name,
    pd.bio_info,
    rt.aka_name,
    rt.movie_title,
    rt.production_year,
    mk.keywords_list
FROM 
    PersonDetails pd
JOIN 
    RankedTitles rt ON pd.person_id = rt.aka_id
LEFT JOIN 
    MovieKeywords mk ON rt.title_id = mk.movie_id
WHERE 
    rt.rank <= 3;
