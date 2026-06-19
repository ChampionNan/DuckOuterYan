
WITH RECURSIVE MovieHierarchy AS (
    SELECT 
        mt.id AS movie_id,
        mt.title,
        mt.production_year,
        NULL AS parent_id
    FROM 
        aka_title mt
    WHERE 
        mt.episode_of_id IS NULL  
    UNION ALL
    SELECT 
        e.id AS movie_id,
        e.title,
        e.production_year,
        mh.movie_id AS parent_id
    FROM 
        aka_title e
    JOIN 
        MovieHierarchy mh ON e.episode_of_id = mh.movie_id  
),
RankedRoles AS (
    SELECT 
        ci.movie_id,
        ci.person_id,
        ci.role_id,
        ROW_NUMBER() OVER (PARTITION BY ci.movie_id ORDER BY ci.nr_order) AS role_rank
    FROM 
        cast_info ci
    WHERE 
        ci.note IS NULL  
),
CompanyStats AS (
    SELECT 
        mc.movie_id,
        co.name AS company_name,
        ct.kind AS company_type,
        COUNT(*) AS company_count
    FROM 
        movie_companies mc
    JOIN 
        company_name co ON mc.company_id = co.id
    JOIN 
        company_type ct ON mc.company_type_id = ct.id
    GROUP BY 
        mc.movie_id, co.name, ct.kind
),
CombinedData AS (
    SELECT 
        mh.movie_id,
        mh.title,
        mh.production_year,
        rr.person_id,
        rr.role_id,
        cs.company_name,
        cs.company_type,
        cs.company_count
    FROM 
        MovieHierarchy mh
    LEFT JOIN 
        RankedRoles rr ON mh.movie_id = rr.movie_id
    LEFT JOIN 
        CompanyStats cs ON mh.movie_id = cs.movie_id
)

SELECT 
    cd.movie_id,
    cd.title,
    cd.production_year,
    cd.person_id,
    cd.role_id,
    cd.company_name,
    cd.company_type,
    COALESCE(cd.company_count, 0) AS company_count,
    CASE 
        WHEN cd.role_id IS NULL THEN 'Uncredited role'
        ELSE 'Credited role'
    END AS role_status
FROM 
    CombinedData cd
WHERE 
    cd.production_year > 2000;
