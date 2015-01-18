/* Crypto - UI */

Mailpile.UI.Crypto.ScoreColor = function(score) {

  var score_color = 'color-01-gray-mid';

  if (score >= 5) {
    score_color = 'color-08-green';
  } else if (score < 5 && score > 2) {
    score_color = 'color-06-blue';
  } else if (score <= 2 && score >= 0) {
    score_color = 'color-09-yellow';
  } else if (score < 2 && score > -3) {
    score_color = 'color-10-orange';
  } else if (score < -3) {
    score_color = 'color-12-red';
  }

  return score_color;
}