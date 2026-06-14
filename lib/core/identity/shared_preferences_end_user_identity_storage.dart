import 'package:shared_preferences/shared_preferences.dart';

import 'end_user_identity_store.dart';

class SharedPreferencesEndUserIdentityStorage
    implements EndUserIdentityStorage {
  SharedPreferencesEndUserIdentityStorage([SharedPreferencesAsync? preferences])
      : preferences = preferences ?? SharedPreferencesAsync();

  final SharedPreferencesAsync preferences;

  @override
  Future<String?> read(String key) {
    return preferences.getString(key);
  }

  @override
  Future<void> write(String key, String value) {
    return preferences.setString(key, value);
  }
}
