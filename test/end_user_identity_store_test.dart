import 'package:flutter_test/flutter_test.dart';
import 'package:short_drama_whitelabel/core/identity/end_user_identity_store.dart';
import 'package:short_drama_whitelabel/flavor/flavor.dart';

void main() {
  test('persists one anonymous end-user reference per tenant app bundle',
      () async {
    final storage = MemoryEndUserIdentityStorage();
    var issuedRefs = 0;
    final store = EndUserIdentityStore(
      storage: storage,
      generator: (flavor) {
        issuedRefs += 1;
        return 'anon:${flavor.brand.tenantCode}-install-$issuedRefs';
      },
    );

    final firstHongguoRef = await store.resolve(FlavorConfig.hongguo());
    final secondHongguoRef = await store.resolve(FlavorConfig.hongguo());
    final douyinRef = await store.resolve(FlavorConfig.douyin());

    expect(firstHongguoRef, 'anon:goldfruit-install-1');
    expect(secondHongguoRef, firstHongguoRef);
    expect(douyinRef, 'anon:pulsedrama-install-2');
    expect(issuedRefs, 2);
    expect(
      storage.snapshot.keys,
      contains('short_drama.end_user_ref.v1.com.shortdrama.goldfruit'),
    );
    expect(
      storage.snapshot.keys,
      contains('short_drama.end_user_ref.v1.com.shortdrama.pulse'),
    );
  });

  test('generated anonymous references are tenant-scoped and not deterministic',
      () {
    final first = EndUserIdentityStore.generateAnonymousRef(
      FlavorConfig.hongguo(),
    );
    final second = EndUserIdentityStore.generateAnonymousRef(
      FlavorConfig.hongguo(),
    );

    expect(first, startsWith('anon:goldfruit-'));
    expect(second, startsWith('anon:goldfruit-'));
    expect(first, isNot('anon:goldfruit-device'));
    expect(second, isNot(first));
  });
}
