import 'package:flutter/material.dart';

import 'app/short_drama_app.dart';
import 'core/identity/end_user_identity_store.dart';
import 'core/identity/shared_preferences_end_user_identity_storage.dart';
import 'flavor/flavor.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final flavor = FlavorConfig.fromEnvironment();
  final endUserRef = await EndUserIdentityStore(
    storage: SharedPreferencesEndUserIdentityStorage(),
  ).resolve(flavor);

  runApp(
    ShortDramaApp(
      flavor: flavor,
      endUserRef: endUserRef,
      loadRemoteConfig: true,
    ),
  );
}
