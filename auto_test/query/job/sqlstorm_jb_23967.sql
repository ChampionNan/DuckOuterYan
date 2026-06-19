WITH RECURSIVE movie_hierarchy AS (
    SELECT 
        t.id AS movie_id,
        t.title,
        t.production_year,
        t.kind_id,
        1 AS level
    FROM 
        aka_title t
    WHERE 
        t.production_year IS NOT NULL
    UNION ALL
    SELECT 
        t.id AS movie_id,
        t.title,
        t.production_year,
        t.kind_id,
        level + 1
    FROM 
        movie_link ml
    JOIN 
        aka_title t ON ml.linked_movie_id = t.id
    JOIN 
        movie_hierarchy mh ON ml.movie_id = mh.movie_id
    WHERE 
        mh.level < 3
),
company_info AS (
    SELECT 
        mc.movie_id,
        c.name AS company_name,
        ct.kind AS company_type,
        ROW_NUMBER() OVER (PARTITION BY mc.movie_id ORDER BY c.name) AS rn
    FROM 
        movie_companies mc
    JOIN 
        company_name c ON mc.company_id = c.id
    JOIN 
        company_type ct ON mc.company_type_id = ct.id
),
actor_info AS (
    SELECT 
        ci.movie_id,
        ak.name AS actor_name,
        ci.nr_order,
        ROW_NUMBER() OVER (PARTITION BY ci.movie_id ORDER BY ci.nr_order) AS actor_rn
    FROM 
        cast_info ci
    JOIN 
        aka_name ak ON ci.person_id = ak.person_id
),
keywords_info AS (
    SELECT 
        mk.movie_id,
        k.keyword,
        ROW_NUMBER() OVER (PARTITION BY mk.movie_id ORDER BY k.keyword) AS keyword_rn
    FROM 
        movie_keyword mk
    JOIN 
        keyword k ON mk.keyword_id = k.id
),
movies_summary AS (
    SELECT 
        mh.movie_id,
        mh.title,
        mh.production_year,
        ci.company_name,
        ci.company_type,
        ak.actor_name,
        ko.keyword,
        COALESCE(mh.level, 0) AS hierarchy_level
    FROM 
        movie_hierarchy mh
    LEFT JOIN 
        company_info ci ON mh.movie_id = ci.movie_id AND ci.rn = 1
    LEFT JOIN 
        actor_info ak ON mh.movie_id = ak.movie_id AND ak.actor_rn = 1
    LEFT JOIN 
        keywords_info ko ON mh.movie_id = ko.movie_id AND ko.keyword_rn = 1
    WHERE 
        mh.production_year > (SELECT AVG(production_year) FROM aka_title WHERE production_year IS NOT NULL)
)
SELECT 
    ms.title,
    ms.production_year,
    ms.company_name,
    ms.company_type,
    ms.actor_name,
    ms.keyword,
    CASE 
        WHEN ms.hierarchy_level > 1 THEN 'Part of a Series'
        WHEN ms.hierarchy_level = 1 THEN 'Standalone Movie'
        ELSE 'Unknown'
    END AS movie_classification
FROM 
    movies_summary ms;
