
WITH RECURSIVE MovieHierarchy AS (
    SELECT 
        mt.id AS movie_id,
        mt.title,
        mt.production_year,
        0 AS level,
        '' AS path
    FROM 
        aka_title mt
    WHERE 
        mt.episode_of_id IS NULL

    UNION ALL

    SELECT 
        a.id AS movie_id,
        a.title,
        a.production_year,
        mh.level + 1,
        mh.path || ' -> ' || a.title
    FROM 
        aka_title a
    JOIN 
        MovieHierarchy mh ON a.episode_of_id = mh.movie_id
    WHERE 
        mh.level < 10 
),

RankedMovies AS (
    SELECT 
        h.movie_id,
        h.title,
        h.production_year,
        ROW_NUMBER() OVER (PARTITION BY h.production_year ORDER BY h.title) AS title_rank,
        DENSE_RANK() OVER (ORDER BY h.production_year DESC) AS production_rank
    FROM 
        MovieHierarchy h
),

MovieDetails AS (
    SELECT 
        rm.movie_id,
        rm.title,
        rm.production_year,
        COALESCE(kw.keyword, 'No Keywords') AS keyword,
        COALESCE(CAST(si.info AS VARCHAR), 'No Info') AS movie_info,
        COUNT(ci.person_id) AS cast_count
    FROM 
        RankedMovies rm
    LEFT JOIN 
        movie_keyword mk ON rm.movie_id = mk.movie_id
    LEFT JOIN 
        keyword kw ON mk.keyword_id = kw.id
    LEFT JOIN 
        cast_info ci ON rm.movie_id = ci.movie_id
    LEFT JOIN 
        movie_info mi ON rm.movie_id = mi.movie_id
    LEFT JOIN 
        info_type si ON mi.info_type_id = si.id
    GROUP BY 
        rm.movie_id, rm.title, rm.production_year, kw.keyword, si.info
),

FinalReport AS (
    SELECT 
        md.movie_id,
        md.title,
        md.production_year,
        md.keyword,
        md.movie_info,
        md.cast_count,
        CASE 
            WHEN md.cast_count > 10 THEN 'Ensemble Cast'
            WHEN md.cast_count BETWEEN 5 AND 10 THEN 'Moderate Cast'
            ELSE 'Minimal Cast'
        END AS cast_description,
        RANK() OVER (ORDER BY md.production_year DESC, md.title) AS movie_rank
    FROM 
        MovieDetails md
)

SELECT 
    fr.movie_id,
    fr.title,
    fr.production_year,
    fr.keyword,
    fr.movie_info,
    fr.cast_count,
    fr.cast_description,
    CASE 
        WHEN fr.movie_rank IS NULL THEN 'Rank Not Available'
        ELSE CAST(fr.movie_rank AS VARCHAR)
    END AS rank_display
FROM 
    FinalReport fr
WHERE 
    fr.production_year BETWEEN 2000 AND 2023;
