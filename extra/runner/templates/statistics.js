/* Calculates a Wilson score confidence interval[1] which gives a percentage
   range of within which there is a 95% chance that the "true" proportion will
   lie within.

   This is useful when investigating low-reproducability defects and reflects
   the fact that the true failure rate is much better known after running more
   tests.  e.g. for a defect with 10% the reproducability you may measure with
   a certain number of test results:

    Runs    Failures   Successes   Failure Rate   Wilson Interval
   --------------------------------------------------------------
        1          0           1          0.00%    0.00% - 79.35%
       10          2           8         20.00%    5.67% - 50.98%
      100          8          92          8.00%    4.48% - 16.24%
     1000        100         900         10.00%    8.29% - 12.02%
    10000       1001        8999         10.01%    9.44% - 10.61%

   Given the increasing number of runs the Wilson score interval describes both
   the value and the certainty of the true reproducability far better than the
   rate as a percentage.

   The wilson score interval is only valid for independant measurements.  e.g.
   if a test fails completely randomly the wilson interval is useful.  It is
   potentially misleading if the failures are e.g. dependant on the time of day
   for example.

   Inputs:
       pos - The number of measurements (test runs) in a particular category
             e.g. number of failures/successes or perhaps number of failures of
             a particular type
       n - The number of measurements (test runs)

   Outputs:
       An array [lower bound, upper bound] of the Wilson score confidence
       interval at 95% confidence.

   [1]: https://en.wikipedia.org/wiki/Binomial_proportion_confidence_interval#Wilson_score_interval

   >>> v = wilson_score_interval_95(0, 1); v[0].toFixed(4) + ", " + v[1].toFixed(4);
   0.0000, 0.7935
   >>> v = wilson_score_interval_95(2, 10); v[0].toFixed(4) + ", " + v[1].toFixed(4);
   0.0567, 0.5098
   >>> v = wilson_score_interval_95(8, 100); v[0].toFixed(4) + ", " + v[1].toFixed(4);
   0.0411, 0.1500
   >>> v = wilson_score_interval_95(100, 1000); v[0].toFixed(4) + ", " + v[1].toFixed(4);
   0.0829, 0.1202
   >>> v = wilson_score_interval_95(1001, 10000); v[0].toFixed(4) + ", " + v[1].toFixed(4);
   0.0944, 0.1061
*/
function wilson_score_interval_95(pos, n) {
    var z, phat, centre, width;
    
    /* z is the (1 - ½α) percentile of a standard normal distribution[1].  In
       this case it has been calculated for a 95% confidence.
       
       [1]: https://en.wikipedia.org/wiki/Binomial_proportion_confidence_interval#Normal_approximation_interval */
    var z = 1.96;
    var phat = 1. * pos / n;

    var centre = (n*phat + z*z/2)/(n+z*z);
    var radius = (z * Math.sqrt((phat*(1-phat)+z*z/(4*n))/n))/(1+z*z/n);
    return [ pos == 0 ? 0.0 : (centre - radius),
             pos == n ? 1.0 : (centre + radius) ];
}

