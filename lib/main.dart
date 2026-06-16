import 'package:flutter/material.dart';

import 'app/short_drama_app.dart';
import 'app/preview_app.dart';
import 'core/identity/end_user_identity_store.dart';
import 'core/identity/shared_preferences_end_user_identity_storage.dart';
import 'flavor/flavor.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final flavor = FlavorConfig.fromEnvironment();
  const previewScreen = String.fromEnvironment('APP_PREVIEW_SCREEN');
  const previewLocale = String.fromEnvironment('APP_PREVIEW_LOCALE');
  if (previewScreen.isNotEmpty) {
    runApp(
      PreviewApp(
        flavor: flavor,
        screenId: previewScreen,
        localeCode: previewLocale.isEmpty ? null : previewLocale,
      ),
    );
    return;
  }
  final endUserRef = await EndUserIdentityStore(
    storage: SharedPreferencesEndUserIdentityStorage(),
  ).resolve(flavor);

  runApp(
    ShortDramaApp(
      flavor: flavor,
      endUserRef: endUserRef,
      loadRemoteConfig: const bool.fromEnvironment(
        'LOAD_REMOTE_CONFIG',
        defaultValue: true,
      ),
    ),
  );
}
