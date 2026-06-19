
WITH RankedTitles AS (
    SELECT 
        t.id AS title_id,
        t.title,
        t.production_year,
        k.keyword,
        ROW_NUMBER() OVER (PARTITION BY k.keyword ORDER BY t.production_year DESC) AS rnk
    FROM 
        aka_title AS t
    JOIN 
        movie_keyword AS mk ON t.id = mk.movie_id
    JOIN 
        keyword AS k ON mk.keyword_id = k.id
    WHERE 
        t.production_year IS NOT NULL
), 
HighestRankedTitles AS (
    SELECT 
        rt.title_id,
        rt.title,
        rt.production_year,
        rt.keyword
    FROM 
        RankedTitles AS rt
    WHERE 
        rt.rnk = 1
), 
MovieDetails AS (
    SELECT 
        ht.title AS title,
        ht.production_year,
        c.name AS company_name,
        ci.note AS cast_note,
        STRING_AGG(DISTINCT a.name, ', ' ORDER BY a.name) AS actor_names
    FROM 
        HighestRankedTitles AS ht
    LEFT JOIN 
        movie_companies AS mc ON ht.title_id = mc.movie_id
    LEFT JOIN 
        company_name AS c ON mc.company_id = c.id
    LEFT JOIN 
        complete_cast AS cc ON ht.title_id = cc.movie_id
    LEFT JOIN 
        cast_info AS ci ON cc.subject_id = ci.person_id
    LEFT JOIN 
        aka_name AS a ON ci.person_id = a.person_id
    GROUP BY 
        ht.title_id, ht.title, ht.production_year, c.name, ci.note
)
SELECT 
    md.title,
    md.production_year,
    md.company_name,
    md.cast_note,
    md.actor_names
FROM 
    MovieDetails AS md;
