; E52 symbolic mirror of the frozen Python promotion governor.
(= (promote-base $supported $gain $regret)
   (if (== $supported 1)
       (if (> $gain 0)
           (if (>= $regret 0) True False)
           False)
       False))

; Deliberately weakened mutations used as negative controls.
(= (promote-ignore-support $supported $gain $regret)
   (if (> $gain 0)
       (if (>= $regret 0) True False)
       False))

(= (promote-ignore-regret $supported $gain $regret)
   (if (== $supported 1)
       (if (> $gain 0) True False)
       False))

; Experiment lineage and evidence dependencies.
(parent E39 E38)
(parent E41 E39)
(parent E43 E41)
(parent E45 E41)
(parent E49 E41)
(audited-by E43 E44)
(revised-by E44 E45)
(rejected-by E50 E51)
