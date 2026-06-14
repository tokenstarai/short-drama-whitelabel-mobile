import 'dart:math';

import '../../flavor/flavor.dart';

abstract class EndUserIdentityStorage {
  Future<String?> read(String key);

  Future<void> write(String key, String value);
}

typedef EndUserRefGenerator = String Function(FlavorConfig flavor);

class EndUserIdentityStore {
  EndUserIdentityStore({
    required this.storage,
    EndUserRefGenerator? generator,
  }) : generator = generator ?? generateAnonymousRef;

  static const storagePrefix = 'short_drama.end_user_ref.v1';

  final EndUserIdentityStorage storage;
  final EndUserRefGenerator generator;

  Future<String> resolve(FlavorConfig flavor) async {
    final key = storageKeyFor(flavor);
    final existing = (await storage.read(key))?.trim();
    if (existing != null && existing.isNotEmpty) {
      return existing;
    }

    final next = generator(flavor).trim();
    if (next.isEmpty) {
      throw StateError('Generated end-user reference must not be empty.');
    }
    await storage.write(key, next);
    return next;
  }

  static String storageKeyFor(FlavorConfig flavor) {
    final bundleId = flavor.brand.bundleId.trim();
    final raw = bundleId.isEmpty ? flavor.brand.tenantCode : bundleId;
    return '$storagePrefix.${_storageKeySegment(raw)}';
  }

  static String generateAnonymousRef(FlavorConfig flavor) {
    final tenantSlug = tenantSlugFor(flavor);
    final issuedAt = DateTime.now().millisecondsSinceEpoch.toRadixString(36);
    final nonce = _randomToken(14);
    return 'anon:$tenantSlug-$issuedAt-$nonce';
  }

  static String tenantSlugFor(FlavorConfig flavor) {
    return _slug(flavor.brand.tenantCode, fallback: 'tenant');
  }

  static String _randomToken(int length) {
    final random = Random.secure();
    final buffer = StringBuffer();
    for (var index = 0; index < length; index += 1) {
      buffer.write(random.nextInt(36).toRadixString(36));
    }
    return buffer.toString();
  }
}

class MemoryEndUserIdentityStorage implements EndUserIdentityStorage {
  MemoryEndUserIdentityStorage([Map<String, String>? seed])
      : _values = {...?seed};

  final Map<String, String> _values;

  Map<String, String> get snapshot => Map.unmodifiable(_values);

  @override
  Future<String?> read(String key) async {
    return _values[key];
  }

  @override
  Future<void> write(String key, String value) async {
    _values[key] = value;
  }
}

String _slug(String value, {required String fallback}) {
  final slug = value
      .toLowerCase()
      .replaceAll(RegExp(r'[^a-z0-9]+'), '-')
      .replaceAll(RegExp(r'^-+|-+$'), '');
  return slug.isEmpty ? fallback : slug;
}

String _storageKeySegment(String value) {
  final segment = value
      .toLowerCase()
      .replaceAll(RegExp(r'[^a-z0-9._-]+'), '-')
      .replaceAll(RegExp(r'^[._-]+|[._-]+$'), '');
  return segment.isEmpty ? 'app' : segment;
}
