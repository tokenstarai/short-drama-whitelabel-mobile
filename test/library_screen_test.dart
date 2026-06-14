import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:short_drama_whitelabel/app/app_runtime.dart';
import 'package:short_drama_whitelabel/core/api/tenant_adapter_client.dart';
import 'package:short_drama_whitelabel/features/account/account_screen.dart';
import 'package:short_drama_whitelabel/flavor/flavor.dart';

class LibraryFakeTransport implements AdapterTransport {
  @override
  Future<AdapterResponse> send(AdapterRequest request) {
    throw StateError('Library screen tests should not call Tenant Edge.');
  }
}

void main() {
  testWidgets('watch history tile opens an empty history state', (
    tester,
  ) async {
    final flavor = FlavorConfig.hongguo();
    final runtime = AppRuntime(
      flavor: flavor,
      client: TenantAdapterClient(
        baseUri: Uri.parse('https://tenant-edge.example.test'),
        transport: LibraryFakeTransport(),
      ),
    );
    addTearDown(runtime.dispose);

    await tester.pumpWidget(
      AppRuntimeScope(
        runtime: runtime,
        child: MaterialApp(home: AccountScreen(flavor: flavor)),
      ),
    );

    await tester.tap(find.text('Watch History'));
    await tester.pumpAndSettle();

    expect(find.text('No watched episodes yet'), findsOneWidget);
  });

  testWidgets('favorites tile opens an empty favorites state', (
    tester,
  ) async {
    final flavor = FlavorConfig.hongguo();
    final runtime = AppRuntime(
      flavor: flavor,
      client: TenantAdapterClient(
        baseUri: Uri.parse('https://tenant-edge.example.test'),
        transport: LibraryFakeTransport(),
      ),
    );
    addTearDown(runtime.dispose);

    await tester.pumpWidget(
      AppRuntimeScope(
        runtime: runtime,
        child: MaterialApp(home: AccountScreen(flavor: flavor)),
      ),
    );

    await tester.tap(find.text('Favorites'));
    await tester.pumpAndSettle();

    expect(find.text('No favorites yet'), findsOneWidget);
  });
}
