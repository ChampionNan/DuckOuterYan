WITH movie_cast AS (
    SELECT 
        t.title AS movie_title,
        t.production_year,
        a.name AS actor_name,
        cc.kind AS role,
        ROW_NUMBER() OVER (PARTITION BY t.id ORDER BY ca.nr_order) AS cast_order
    FROM
        aka_title t
    JOIN
        cast_info ca ON ca.movie_id = t.id
    JOIN
        aka_name a ON ca.person_id = a.person_id
    JOIN
        comp_cast_type cc ON ca.role_id = cc.id
    WHERE 
        a.name IS NOT NULL
        AND t.production_year >= 2000
),

keyword_movie AS (
    SELECT 
        t.id AS movie_id,
        STRING_AGG(k.keyword, ', ') AS keywords
    FROM
        aka_title t
    JOIN
        movie_keyword mk ON t.id = mk.movie_id
    JOIN
        keyword k ON mk.keyword_id = k.id
    GROUP BY 
        t.id
),

company_movie AS (
    SELECT 
        t.title,
        c.name AS company_name,
        ct.kind AS company_type,
        ROW_NUMBER() OVER (PARTITION BY t.id ORDER BY cm.note DESC NULLS LAST) AS company_order
    FROM 
        aka_title t
    JOIN 
        movie_companies cm ON t.id = cm.movie_id
    JOIN 
        company_name c ON cm.company_id = c.id
    JOIN
        company_type ct ON cm.company_type_id = ct.id
    WHERE 
        ct.kind IS NOT NULL
)

SELECT 
    mc.movie_title,
    mc.production_year,
    mc.actor_name,
    mc.role,
    km.keywords,
    c.company_name,
    c.company_type
FROM 
    movie_cast mc
LEFT JOIN 
    keyword_movie km ON mc.production_year = km.movie_id
FULL OUTER JOIN 
    company_movie c ON mc.movie_title = c.title
WHERE 
    (mc.cast_order <= 3 OR mc.role IS NULL)
    AND (c.company_order IS NOT NULL OR c.company_name IS NULL);
