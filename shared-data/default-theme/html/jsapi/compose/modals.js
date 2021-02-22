/* Modals - Composer */

// SPDX-FileCopyrightText: 2011-2015  Bjarni R. Einarsson, Mailpile ehf and friends
// SPDX-License-Identifier: AGPL-3.0-or-later

Mailpile.UI.Modals.ComposerEncryptionHelper = function(mid, determine) {
  Mailpile.API.with_template('modal-composer-encryption-helper', function(modal) {
    determine['mid'] = mid;
    Mailpile.UI.show_modal(modal(determine));
  });
};
